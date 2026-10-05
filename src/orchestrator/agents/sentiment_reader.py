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
            logger.debug(f"SentimentReader 评论拉取跳过: {exc}")
            return {}

    # ── Few-Shot 示例庫（6 好 + 2 壞）──────────────────────
    _FEWSHOT_GOOD = [
        {"comment_count": "多（>50条）", "sentiment": "mixed",
         "positive_pct": 45, "neutral_pct": 25, "negative_pct": 30,
         "confidence": "high", "monetization_signals": "评论区8人问购买渠道，3人已下单并晒单，2人抱怨发货慢",
         "insights": "正面集中于产品性价比（'这个价位很值''比XX品牌便宜一半'），负面集中于发货速度（'等了10天'），核心矛盾在供应链而非产品力",
         "reaction": "购买意愿强烈但物流体验影响复购口碑"},
        {"comment_count": "多（>50条）", "sentiment": "positive",
         "positive_pct": 78, "neutral_pct": 15, "negative_pct": 7,
         "confidence": "high", "monetization_signals": "评论区5人表示'已买''好用'，多人@朋友来看，2人问链接",
         "insights": "压倒性好评集中在'效果明显''性价比高'，tag朋友行为说明社交传播力强；7%负评为个别品控问题",
         "reaction": "压倒性好评+自发社交传播，适合加大投放"},
        {"comment_count": "少（<10条）", "sentiment": "positive",
         "positive_pct": 80, "neutral_pct": 20, "negative_pct": 0,
         "confidence": "low", "monetization_signals": "评论量太少（仅5条），无法判断真实购买意愿",
         "insights": "虽正面比例高但样本极少（仅5条评论），统计无意义；播放高但评论低说明内容可能缺乏讨论点或互动引导不足",
         "reaction": "受众被动消费无参与感，需在内容中加入讨论引导"},
        {"comment_count": "多（>50条）", "sentiment": "negative",
         "positive_pct": 12, "neutral_pct": 18, "negative_pct": 70,
         "confidence": "high", "monetization_signals": "无人表达购买意愿，多人劝退，5人表示'后悔买了'",
         "insights": "负评集中在产品质量差+售后无回应，内容引发负面口碑传播；对品牌方是危机信号，对竞品是切入机会",
         "reaction": "负评风暴，品牌需危机公关；竞品可借机推出对比内容"},
        {"comment_count": "零评论", "sentiment": "unknown",
         "positive_pct": 0, "neutral_pct": 0, "negative_pct": 0,
         "confidence": "low", "monetization_signals": "无评论数据",
         "insights": "无任何评论，无法进行情绪分析。可能原因：内容新发布、评论区关闭、或内容缺乏互动性",
         "reaction": "无受众反应数据，无法判断"},
        {"comment_count": "中（10-50条）", "sentiment": "mixed",
         "positive_pct": 55, "neutral_pct": 20, "negative_pct": 25,
         "confidence": "medium", "monetization_signals": "评论区3人问'多少钱''在哪买'，1人表示价格超出预算",
         "insights": "正面多为认可内容质量（'讲得好详细'），负面集中于价格敏感性；购买意愿存在但价格是主要障碍",
         "reaction": "内容质量获认可，价格定位需优化以转化潜在买家"},
    ]

    _FEWSHOT_BAD = [
        {"comment_count": "少（<10条）", "sentiment": "positive",
         "positive_pct": 80, "neutral_pct": 20, "negative_pct": 0,
         "confidence": "high", "monetization_signals": "正面情绪高，适合带货",
         "insights": "❌ 错误1：5条评论就给high confidence——评论<10时必须low",
         "reaction": "教训：样本量决定置信度，不能为了好看而虚标high"},
        {"comment_count": "中（10-50条）", "sentiment": "positive",
         "positive_pct": 60, "neutral_pct": 30, "negative_pct": 10,
         "confidence": "medium", "monetization_signals": "未提及",
         "insights": "❌ 错误2：分析完全忽略评论区的购买意愿信号（'在哪买''多少钱'），只看了情绪没看消费意图",
         "reaction": "教训：monetization_signals 字段必须扫描购买关键词，无信号也要明确标注「无明显购买信号」"},
    ]

    async def _llm_generate(
        self, items: list, platform: str, comments_data: dict
    ) -> SentimentReport:
        """DeepSeek LLM 分析評論情緒（v2 增強 prompt）。"""
        items_text = "\n".join(
            f"{i}. {it.get('title','')} | 播放:{it.get('plays','0')} | 赞:{it.get('likes','0')}"
            + (f" | 评论:{comments_data.get(it.get('platform_id','') or it.get('bvid',''), [])[:5]}"
               if comments_data.get(it.get('platform_id','') or it.get('bvid','')) else "")
            for i, it in enumerate(items[:10])
        )

        good_examples_text = "\n".join(
            f"  ✅ 评论量: {ex['comment_count']} | 情绪: {ex['sentiment']} | 置信度: {ex['confidence']}\n     P:{ex['positive_pct']}% N:{ex['neutral_pct']}% Neg:{ex['negative_pct']}%\n     购买信号: {ex['monetization_signals']}\n     洞察: {ex['insights']}\n     受众反应: {ex['reaction']}"
            for ex in self._FEWSHOT_GOOD
        )
        bad_examples_text = "\n".join(
            f"  ❌ 评论量: {ex['comment_count']} | 情绪: {ex['sentiment']} | 置信度: {ex['confidence']}\n     洞察: {ex['insights']}\n     受众反应: {ex['reaction']}"
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

## 负例
{bad_examples_text}
</examples>

<task>
分析以下内容的受众情绪反应：
{items_text}
</task>

<output_format>
返回纯 JSON：
{{"overall_sentiment": "positive/neutral/negative/mixed",
 "summary": "整体结论（30字以上）",
 "items": [{{"index": 数字,
   "sentiment": "positive/neutral/negative/mixed",
   "positive_pct": 0-100, "neutral_pct": 0-100, "negative_pct": 0-100,
   "key_insights": "引用具体评论的洞察（30字以上，零评论时说明原因）",
   "audience_reaction": "受众反应摘要（20字以上）",
   "confidence": "high/medium/low",
   "monetization_signals": "购买信号描述（30字以上，含信号类型+数量，无则标注原因）"}}]}}
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
            logger.warning(f"SentimentReader LLM 失败: {exc}")
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
            summary="LLM 不可用，降级模式",
        )
