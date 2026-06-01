"""Sentiment Reader Agent — 評論情緒分析。

Flow:
  1. 接收內容列表，拉取評論
  2. DeepSeek LLM 分析情緒分佈 + 關鍵洞察
  3. 輸出情緒報告

用法:
  reader = SentimentReader()
  report = await reader.run(items=trend_items, platform="bilibili")
"""

import json
from dataclasses import dataclass, field, asdict

from typing import Literal
from pydantic import BaseModel, Field

from src.orchestrator.agents.base import BaseAgent
from src.utils.logger import logger


# ── Pydantic 结构化输出模型 ─────────────────────────────────

class SentimentItemOutput(BaseModel):
    index: int = Field(description="内容在输入列表中的索引")
    sentiment: Literal["positive", "neutral", "negative", "mixed", "unknown"] = Field(description="情绪标签")
    positive_pct: float = Field(ge=0, le=100, description="正面评论百分比")
    neutral_pct: float = Field(ge=0, le=100, description="中性评论百分比")
    negative_pct: float = Field(ge=0, le=100, description="负面评论百分比")
    key_insights: str = Field(default="", description="关键洞察，30字以上，引用具体评论佐证。无评论数据时可为空")
    audience_reaction: str = Field(default="", description="受众反应一句话，20字以上")
    confidence: Literal["high", "medium", "low"] = Field(description="置信度：high(>=30条)/medium(10-29条)/low(<10条)")
    monetization_signals: str = Field(default="", description="购买意愿信号描述，30字以上，含具体信号类型+数量。无评论数据时可为空")


class SentimentReaderOutput(BaseModel):
    overall_sentiment: Literal["positive", "neutral", "negative", "mixed", "unknown"] = Field(description="整体情绪倾向（零评论时为unknown）")
    summary: str = Field(min_length=30, description="一句话总结，含情绪主导方向+关键发现")
    items: list[SentimentItemOutput] = Field(description="情绪分析列表")


@dataclass
class SentimentItem:
    title: str
    platform: str
    sentiment: str = ""           # positive / neutral / negative / mixed
    positive_pct: float = 0.0
    neutral_pct: float = 0.0
    negative_pct: float = 0.0
    key_insights: str = ""        # 關鍵洞察
    audience_reaction: str = ""   # 受眾反應摘要
    confidence: str = "medium"    # high/medium/low — 基於評論樣本量
    monetization_signals: str = ""  # 購買意願信號


@dataclass
class SentimentReport:
    platform: str
    total_analyzed: int
    items: list[SentimentItem] = field(default_factory=list)
    overall_sentiment: str = ""
    summary: str = ""


class SentimentReader(BaseAgent):
    """評論情緒分析 Agent。"""

    async def run(self, items: list, platform: str = "", fetch_comments: bool = True,
                  pre_harvested: dict = None) -> SentimentReport:
        """主入口。

        Args:
            items: 內容列表 (dict with title/platform_id)
            platform: 平台名
            fetch_comments: 是否拉取真實評論 (需 CDP browser)
            pre_harvested: Pipeline 预收割的评论 {platform_id: [comments]}
        """
        if not items:
            return SentimentReport(platform=platform, total_analyzed=0)

        # 优先用预收割评论，其次自行拉取
        comments_data = {}
        if pre_harvested:
            for item in items:
                item_id = (item.get("platform_id") or item.get("bvid")
                           or item.get("aweme_id") or item.get("note_id") or "")
                if item_id and item_id in pre_harvested:
                    comments_data[item_id] = pre_harvested[item_id]
        elif fetch_comments:
            comments_data = await self._fetch_comments(items, platform)

        if not self._api_key:
            return self._fallback(items, platform, comments_data)

        return await self._llm_generate(items, platform, comments_data)

    async def as_node(self, state: dict) -> dict:
        trend_reports = state.get("trend_reports", {})
        harvested = state.get("harvested_comments", {})
        all_sentiments = []
        summaries = []

        for p, report_dict in trend_reports.items():
            items = report_dict.get("items", [])
            if items:
                raw_items = [it.get("raw", {}) for it in items if isinstance(it, dict)]
                # 用 Pipeline 预收割的评论（key=platform_id），直接传入不重复拉取
                report = await self.run(
                    items=raw_items[:5], platform=p,
                    fetch_comments=False,
                    pre_harvested=harvested,
                )
                all_sentiments.extend(report.items)
                if report.summary:
                    summaries.append(report.summary)

        return {"sentiment_report": asdict(SentimentReport(
            platform="all",
            total_analyzed=len(all_sentiments),
            items=all_sentiments,
            summary=" | ".join(summaries) if summaries else "",
        ))}

    # ── internal ──────────────────────────────────────────────

    async def _fetch_comments(self, items: list, platform: str) -> dict[str, list[str]]:
        """拉取真實評論。"""
        try:
            from src.orchestrator.nodes import _get_adapter
            adapter = _get_adapter(platform)
            result = {}
            for item in items[:5]:
                item_id = (
                    item.get("platform_id") or item.get("bvid")
                    or item.get("aweme_id") or item.get("note_id") or ""
                )
                if not item_id:
                    continue
                try:
                    comments = await adapter.comment(item_id, limit=10)
                    result[item_id] = [
                        c.get("content", c.get("text", ""))
                        for c in (comments if isinstance(comments, list) else [])
                    ][:10]
                except Exception:
                    continue
            return result
        except Exception as exc:
            logger.debug(f"SentimentReader 評論拉取跳過: {exc}")
            return {}

    # ── Few-Shot 示例庫（6 好 + 2 壞）──────────────────────
    _FEWSHOT_GOOD = [
        {"comment_count": "多（>50條）", "sentiment": "mixed",
         "positive_pct": 45, "neutral_pct": 25, "negative_pct": 30,
         "confidence": "high", "monetization_signals": "評論區8人問購買渠道，3人已下單並曬單，2人抱怨發貨慢",
         "insights": "正面集中於產品性價比（'這個價位很值''比XX品牌便宜一半'），負面集中於發貨速度（'等了10天'），核心矛盾在供應鏈而非產品力",
         "reaction": "購買意願強烈但物流體驗影響復購口碑"},
        {"comment_count": "多（>50條）", "sentiment": "positive",
         "positive_pct": 78, "neutral_pct": 15, "negative_pct": 7,
         "confidence": "high", "monetization_signals": "評論區5人表示'已買''好用'，多人@朋友來看，2人問鏈接",
         "insights": "壓倒性好評集中在'效果明顯''性價比高'，tag朋友行為說明社交傳播力強；7%負評為個別品控問題",
         "reaction": "壓倒性好評+自發社交傳播，適合加大投放"},
        {"comment_count": "少（<10條）", "sentiment": "positive",
         "positive_pct": 80, "neutral_pct": 20, "negative_pct": 0,
         "confidence": "low", "monetization_signals": "評論量太少（僅5條），無法判斷真實購買意願",
         "insights": "雖正面比例高但樣本極少（僅5條評論），統計無意義；播放高但評論低說明內容可能缺乏討論點或互動引導不足",
         "reaction": "受眾被動消費無參與感，需在內容中加入討論引導"},
        {"comment_count": "多（>50條）", "sentiment": "negative",
         "positive_pct": 12, "neutral_pct": 18, "negative_pct": 70,
         "confidence": "high", "monetization_signals": "無人表達購買意願，多人勸退，5人表示'後悔買了'",
         "insights": "負評集中在產品質量差+售後無回應，內容引發負面口碑傳播；對品牌方是危機信號，對競品是切入機會",
         "reaction": "負評風暴，品牌需危機公關；競品可藉機推出對比內容"},
        {"comment_count": "零評論", "sentiment": "unknown",
         "positive_pct": 0, "neutral_pct": 0, "negative_pct": 0,
         "confidence": "low", "monetization_signals": "無評論數據",
         "insights": "無任何評論，無法進行情緒分析。可能原因：內容新發佈、評論區關閉、或內容缺乏互動性",
         "reaction": "無受眾反應數據，無法判斷"},
        {"comment_count": "中（10-50條）", "sentiment": "mixed",
         "positive_pct": 55, "neutral_pct": 20, "negative_pct": 25,
         "confidence": "medium", "monetization_signals": "評論區3人問'多少錢''在哪買'，1人表示價格超出預算",
         "insights": "正面多為認可內容質量（'講得好詳細'），負面集中於價格敏感性；購買意願存在但價格是主要障礙",
         "reaction": "內容質量獲認可，價格定位需優化以轉化潛在買家"},
    ]

    _FEWSHOT_BAD = [
        {"comment_count": "少（<10條）", "sentiment": "positive",
         "positive_pct": 80, "neutral_pct": 20, "negative_pct": 0,
         "confidence": "high", "monetization_signals": "正面情緒高，適合帶貨",
         "insights": "❌ 錯誤1：5條評論就給high confidence——評論<10時必須low",
         "reaction": "教訓：樣本量決定置信度，不能為了好看而虛標high"},
        {"comment_count": "中（10-50條）", "sentiment": "positive",
         "positive_pct": 60, "neutral_pct": 30, "negative_pct": 10,
         "confidence": "medium", "monetization_signals": "未提及",
         "insights": "❌ 錯誤2：分析完全忽略評論區的購買意願信號（'在哪買''多少錢'），只看了情緒沒看消費意圖",
         "reaction": "教訓：monetization_signals 欄位必須掃描購買關鍵詞，無信號也要明確標註「無明顯購買信號」"},
    ]

    async def _llm_generate(
        self, items: list, platform: str, comments_data: dict
    ) -> SentimentReport:
        """DeepSeek LLM 分析評論情緒（v2 增強 prompt）。"""
        items_text = "\n".join(
            f"{i}. {it.get('title','')} | 播放:{it.get('plays','0')} | 讚:{it.get('likes','0')}"
            + (f" | 評論:{comments_data.get(it.get('platform_id','') or it.get('bvid',''), [])[:5]}"
               if comments_data.get(it.get('platform_id','') or it.get('bvid','')) else "")
            for i, it in enumerate(items[:10])
        )

        good_examples_text = "\n".join(
            f"  ✅ 評論量: {ex['comment_count']} | 情緒: {ex['sentiment']} | 置信度: {ex['confidence']}\n     P:{ex['positive_pct']}% N:{ex['neutral_pct']}% Neg:{ex['negative_pct']}%\n     購買信號: {ex['monetization_signals']}\n     洞察: {ex['insights']}\n     受眾反應: {ex['reaction']}"
            for ex in self._FEWSHOT_GOOD
        )
        bad_examples_text = "\n".join(
            f"  ❌ 評論量: {ex['comment_count']} | 情緒: {ex['sentiment']} | 置信度: {ex['confidence']}\n     洞察: {ex['insights']}\n     受眾反應: {ex['reaction']}"
            for ex in self._FEWSHOT_BAD
        )

        total_comments = sum(len(v) for v in comments_data.values())
        prompt = f"""<role>
你是受众情绪分析师（Sentiment Reader）。你的唯一职责：Analyze 评论情绪分布，Classify 每条内容的情绪倾向，Detect 购买意愿信号，Estimate 置信度。
</role>

<scope>
OWN: 情绪分类（positive/neutral/negative/mixed）、购买信号检测、置信度评估
BOUNDARY: 不分析视频内容质量（VideoAnalyst）、不评估爆款潜力（TrendScout）、不生成营销建议（CopyWriter）
ESCALATE: 零评论时 → 全部百分比=0，sentiment=unknown，confidence=low
</scope>

<quality_standards>
专业级输出必须满足：
1. 先逐条分析评论情绪方向，再综合统计百分比（Chain-of-Thought）
2. confidence 严格按评论数：≥30→high，10-29→medium，<10→low
3. 必须扫描购买信号（问价格/问渠道/已下单/劝退），无信号也标注「无购买信号」
4. positive+neutral+negative=100%（零评论除外）
5. 引用至少1条具体评论佐证判断
</quality_standards>

<context>平台：{platform} | 评论数：{total_comments}</context>

<examples>
## 正例
{good_examples_text}

## 負例
{bad_examples_text}
</examples>

<task>
分析以下內容的受眾情緒反應：
{items_text}
</task>

<output_format>
返回純 JSON：
{{"overall_sentiment": "positive/neutral/negative/mixed",
 "summary": "整體結論（30字以上）",
 "items": [{{"index": 數字,
   "sentiment": "positive/neutral/negative/mixed",
   "positive_pct": 0-100, "neutral_pct": 0-100, "negative_pct": 0-100,
   "key_insights": "引用具體評論的洞察（30字以上，零評論時說明原因）",
   "audience_reaction": "受眾反應摘要（20字以上）",
   "confidence": "high/medium/low",
   "monetization_signals": "購買信號描述（30字以上，含信號類型+數量，無則標註原因）"}}]}}
</output_format>"""

        try:
            output = await self._call_llm_with_critic(prompt, SentimentReaderOutput, "sentiment_reader", temperature=0.3)

            sentiment_items = []
            for s in output.items:
                idx = s.index
                src = items[idx] if 0 <= idx < len(items) else {}
                sentiment_items.append(SentimentItem(
                    title=src.get("title", ""),
                    platform=platform,
                    sentiment=s.sentiment,
                    positive_pct=s.positive_pct,
                    neutral_pct=s.neutral_pct,
                    negative_pct=s.negative_pct,
                    key_insights=s.key_insights,
                    audience_reaction=s.audience_reaction,
                    confidence=s.confidence,
                    monetization_signals=s.monetization_signals,
                ))

            return SentimentReport(
                platform=platform,
                total_analyzed=len(sentiment_items),
                items=sentiment_items,
                overall_sentiment=output.overall_sentiment,
                summary=output.summary,
            )
        except Exception as exc:
            logger.warning(f"SentimentReader LLM 失敗: {exc}")
            return self._fallback(items, platform, comments_data)

    def _fallback(self, items: list, platform: str, comments_data: dict = None) -> SentimentReport:
        items_out = [
            SentimentItem(
                title=it.get("title", "")[:50],
                platform=platform,
                sentiment="neutral",
            )
            for it in items[:5]
        ]
        return SentimentReport(
            platform=platform,
            total_analyzed=len(items_out),
            items=items_out,
            summary="LLM 不可用，降級模式",
        )
