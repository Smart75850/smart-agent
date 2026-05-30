"""Content Remixer Agent — 数据分析/总结/改写。

CopyWriter = 原创生成，Remixer = 改写成文。

Mode:
  summarize — 数据总结（一句话摘要 + 关键词 + 平台分布）
  analyze   — 赛道分析（竞争格局 + 内容策略 + 风险提示）
  rewrite   — 跨平台改写（抖音↔小红书↔B站）

用法:
  remixer = ContentRemixer()
  report = await remixer.run(RemixInput(mode="summarize", topic="AI", raw_items=[...]))
"""

import json
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import Literal, Optional

from pydantic import BaseModel, Field

from src.orchestrator.agents.base import BaseAgent
from src.utils.logger import logger


# ── Pydantic 结构化输出模型 ─────────────────────────────────

class TrackInsightOutput(BaseModel):
    topic: str = Field(description="细分赛道名")
    competition_level: Literal["高", "中", "低"] = Field(description="竞争程度：高(头部60%+)/中(头部<40%长尾活跃)/低(无明显头部)")
    entry_barrier: str = Field(min_length=30, description="具体门槛描述，含资金/技术/资源/能力要求")
    opportunity_score: int = Field(ge=0, le=100, description="机会评分")
    recommended_angles: str = Field(min_length=25, description="2-3个具体切入角度，50字以上，含目标人群+差异化点+执行路径")


class ContentRewriteOutput(BaseModel):
    original: str = Field(description="原内容标题/文案")
    source_platform: Literal["douyin", "xiaohongshu", "bilibili", "zhihu", "kuaishou", "weibo", "tieba"] = Field(description="来源平台")
    target_platform: Literal["douyin", "xiaohongshu", "bilibili", "zhihu", "kuaishou", "weibo", "tieba"] = Field(description="目标平台")
    rewritten: str = Field(description="改写后内容")
    changes_summary: str = Field(min_length=15, description="改动说明，30字以上，含语言/节奏/信息密度/情绪四个维度的变化")


class RemixOutput(BaseModel):
    summary: str = Field(description="根据模式不同：摘要/竞争格局总结/改写说明")
    key_keywords: list[str] = Field(default_factory=list, description="关键词列表")
    platform_breakdown: dict[str, int] = Field(default_factory=dict, description="平台分布")
    track_insights: list[TrackInsightOutput] = Field(default_factory=list, description="赛道洞察列表(analyze模式)")
    rewrites: list[ContentRewriteOutput] = Field(default_factory=list, description="改写列表(rewrite模式)")
    recommendations: str = Field(default="", description="策略建议(analyze模式)")


@dataclass
class RemixInput:
    """封装 run() 入参。"""
    mode: str = "summarize"          # summarize / analyze / rewrite
    topic: str = ""
    raw_items: list = field(default_factory=list)
    trend_reports: dict = field(default_factory=dict)
    product_report: dict = field(default_factory=dict)
    video_report: dict = field(default_factory=dict)
    sentiment_report: dict = field(default_factory=dict)


@dataclass
class TrackInsight:
    topic: str = ""
    competition_level: str = ""      # 高/中/低
    entry_barrier: str = ""
    opportunity_score: int = 0       # 0-100
    recommended_angles: str = ""


@dataclass
class ContentRewrite:
    original: str = ""
    source_platform: str = ""
    target_platform: str = ""
    rewritten: str = ""
    changes_summary: str = ""


@dataclass
class RemixReport:
    topic: str
    mode: str
    summary: str = ""
    key_keywords: list[str] = field(default_factory=list)
    platform_breakdown: dict = field(default_factory=dict)
    track_insights: list[TrackInsight] = field(default_factory=list)
    rewrites: list[ContentRewrite] = field(default_factory=list)
    recommendations: str = ""


class ContentRemixer(BaseAgent):
    """数据分析/总结/改写 Agent。"""

    async def run(self, inp: RemixInput) -> RemixReport:
        if not self._api_key:
            return self._fallback(inp)

        return await self._llm_generate(inp)

    async def as_node(self, state: dict) -> dict:
        merged = state.get("merged_items", [])
        scored = state.get("scored_items", [])
        raw_items = scored if scored else merged

        report = await self.run(RemixInput(
            mode="analyze",
            topic=state.get("keyword", ""),
            raw_items=raw_items,
            trend_reports=state.get("trend_reports", {}),
            product_report=state.get("product_report", {}),
            video_report=state.get("video_report", {}),
            sentiment_report=state.get("sentiment_report", {}),
        ))

        return {"remix_report": asdict(report)}

    # ── Few-Shot 示例庫（3 modes × 3-4 例 = 10 good + 2 bad） ─
    _FEWSHOT_GOOD = [
        # -- summarize (3 例) --
        {"mode": "summarize", "topic": "AI繪圖工具",
         "output": {"summary": "AI繪圖賽道正從'能出圖'轉向'精準可控'，Midjourney主導藝術方向而Stable Diffusion在商用API側增長最快，20條內容中12條討論可控性問題",
                    "key_keywords": ["AI繪圖", "Midjourney", "Stable Diffusion", "可控生成", "商用API"],
                    "platform_breakdown": {"bilibili": 8, "xiaohongshu": 6, "douyin": 4, "zhihu": 2}}},
        {"mode": "summarize", "topic": "居家健身",
         "output": {"summary": "居家健身內容在春節後出現明顯高峰，核心話題從'減肥'轉向'體態矯正'，瑜伽墊和彈力帶是最常出現的關聯商品",
                    "key_keywords": ["居家健身", "體態矯正", "瑜伽", "彈力帶", "無器械訓練"],
                    "platform_breakdown": {"douyin": 12, "xiaohongshu": 5, "bilibili": 3}}},
        {"mode": "summarize", "topic": "少數據主題",
         "output": {"summary": "共僅3條相關內容，數據量不足以進行有意義的趨勢判斷。現有內容集中在[平台A]，初步顯示[方向X]的討論，但需更多數據才能確認趨勢",
                    "key_keywords": ["關鍵詞1", "關鍵詞2"],
                    "platform_breakdown": {"douyin": 3}}},

        # -- analyze (4 例) --
        {"mode": "analyze", "topic": "藍牙耳機",
         "output": {"summary": "藍牙耳機賽道頭部集中度高但中腰部仍有細分機會。頭部3個品牌佔據65%內容曝光，但'降噪''運動''低延遲'三個垂直方向各有10-15%長尾創作者活躍。最大機會在'百元內性價比'細分——頭部品牌放棄該價位段，用戶需求旺盛",
                    "track_insights": [{"topic": "藍牙耳機-降噪", "competition_level": "高", "entry_barrier": "需ANC技術儲備+聲學調校經驗，頭部品牌專利壁壘明顯",
                                       "opportunity_score": 35, "recommended_angles": "避開ANC主戰場，切入'通話降噪'細分——技術門檻低+遠程辦公需求大"}],
                    "key_keywords": ["藍牙耳機", "降噪", "性價比", "運動耳機", "低延遲"],
                    "recommendations": "建議從百元價位段切入，主打通話降噪+超長續航兩個實用賣點..."}},
        {"mode": "analyze", "topic": "寵物食品",
         "output": {"summary": "寵物食品賽道增長迅猛但競爭無序，暫無絕對頭部品牌。內容以'成分黨'測評為主導，用戶最關注安全性>性價比>適口性。國產品牌正在取代進口的主導地位",
                    "track_insights": [{"topic": "寵物食品-凍乾", "competition_level": "低", "entry_barrier": "需冷凍乾燥設備（投入約30-80萬）+ 寵物營養學配方能力 + 供應鏈管理",
                                       "opportunity_score": 85, "recommended_angles": "1) 單一肉源低敏配方（市場空白）2) 功能性凍乾（關節/美毛）3) 訂閱制按月配送"}],
                    "key_keywords": ["寵物食品", "凍乾", "成分黨", "國產", "貓糧"],
                    "recommendations": "食品級供應鏈是核心壁壘，建議先OEM測試市場反應再自建產線..."}},
        {"mode": "analyze", "topic": "手機遊戲",
         "output": {"summary": "手遊賽道馬太效應極強，頭部5款遊戲佔據80%+內容流量。新品突圍需至少500萬預算+6個月預熱期。不建議個體創作者/小團隊直接競爭",
                    "track_insights": [{"topic": "手遊-新品發佈", "competition_level": "高", "entry_barrier": "需遊戲研發團隊（至少20人）+ 發行渠道關係 + 至少500萬市場預算",
                                       "opportunity_score": 15, "recommended_angles": "不建議直接入場。可考慮做頭部遊戲的二次創作/攻略/周邊內容，藉助現有流量池"}],
                    "key_keywords": ["手遊", "二次創作", "攻略", "遊戲周邊"],
                    "recommendations": "放棄直接競爭，轉做遊戲內容生態服務商..."}},
        {"mode": "analyze", "topic": "新中式穿搭",
         "output": {"summary": "新中式穿搭處於爆發前夜：搜索量月增長200%+，但目前專業創作者少（<50人活躍），內容供不應求。天貓數據顯示相關商品GMV同比+340%",
                    "track_insights": [{"topic": "新中式穿搭-日常款", "competition_level": "低", "entry_barrier": "需對傳統服飾文化有理解（非硬門檻）+ 供應鏈（可從檔口拿貨起步）+ 視覺審美能力",
                                       "opportunity_score": 93, "recommended_angles": "1) 新中式通勤穿搭（最大痛點：怎麼穿去上班）2) 平價新中式（打破'貴'的認知）3) 微胖/小個子新中式（人群精準）"}],
                    "key_keywords": ["新中式", "穿搭", "國風", "通勤", "平價"],
                    "recommendations": "黃金窗口期6-12個月，建議快速起號搶佔'新中式通勤'這個內容真空地帶..."}},

        # -- rewrite (3 例) --
        {"mode": "rewrite", "topic": "",
         "output": {"rewrites": [{"original": "3個信號告訴你房價要跌了", "source_platform": "douyin",
                                  "target_platform": "xiaohongshu",
                                  "rewritten": "🏠 注意！這3個信號出現，說明房價可能要變天了\n最近多地樓市出現異動，我整理了3個關鍵指標…",
                                  "changes_summary": "從快節奏警告風→小紅書精緻資訊風：加emoji、語氣從'告訴你'變為'說明'、增加上下文鋪墊"}],
                    "summary": "抖音→小紅書改寫：降節奏+加emoji+軟化語氣+增加場景描述"},
         },
        {"mode": "rewrite", "topic": "",
         "output": {"rewrites": [{"original": "✨挖到寶了！這個小眾香薰好聞到犯規 #家居好物",
                                  "source_platform": "xiaohongshu", "target_platform": "bilibili",
                                  "rewritten": "【深度測評】我買了市面上12款小眾香薰，用氣相色譜儀測出了最好聞的一款",
                                  "changes_summary": "從小紅書感性分享→B站硬核測評：去掉emoji、增加數據維度（12款/儀器）、建立專業人設"}],
                    "summary": "小紅書→B站改寫：增加信息密度+數據背書+深度框架"},
         },
        {"mode": "rewrite", "topic": "",
         "output": {"rewrites": [{"original": "【硬核】CPU架構之爭：x86 vs ARM 到底誰會贏？",
                                  "source_platform": "bilibili", "target_platform": "douyin",
                                  "rewritten": "你手機和電腦的晶片，其實在打一場看不見的戰爭⚡\nx86統治了30年，但ARM正在偷家…",
                                  "changes_summary": "從B站深度科普→抖音輕科普：縮短句子+戰爭比喻+emoji+懸念結尾"}],
                    "summary": "B站→抖音改寫：大幅縮短+通俗比喻+保留核心信息點+加入懸念"},
         },
    ]

    _FEWSHOT_BAD = [
        {"mode": "analyze", "topic": "",
         "output": {"summary": "這個賽道競爭很激烈，但也有很多機會",
                    "track_insights": [{"topic": "未細分", "competition_level": "中", "entry_barrier": "需要一定的資金和技術",
                                       "opportunity_score": 50, "recommended_angles": "可以從短視頻入手做內容"}]},
         "why_bad": "❌ 錯誤示範：競爭分析空泛無數據（'激烈'有多激烈？）、entry_barrier 用廢話（'一定資金'是多少？）、機會分永遠50分（不承擔判斷責任）、建議不可執行（'做內容'不是策略）"},
        {"mode": "rewrite", "topic": "",
         "output": {"rewrites": [{"original": "好吃的零食推薦", "source_platform": "douyin", "target_platform": "xiaohongshu",
                                  "rewritten": "好吃的零食推薦✨", "changes_summary": "加了emoji"}],
                    "summary": "改寫完成"},
         "why_bad": "❌ 錯誤示範：改寫僅加emoji不叫跨平台適配——不同平台的語言習慣、信息密度、情緒基調都要相應調整"},
    ]

    async def _llm_generate(self, inp: RemixInput) -> RemixReport:
        """DeepSeek LLM 數據分析/總結/改寫（v2 增強 prompt）。"""
        context_parts = [f"主题: {inp.topic or '通用'}"]
        if inp.raw_items:
            titles = [it.get("title", "")[:50] for it in inp.raw_items[:10]]
            context_parts.append(f"原始内容: {'; '.join(titles)}")

        platform_counts = Counter(
            it.get("platform", "unknown") for it in inp.raw_items
        )
        context_parts.append(f"平台分布: {dict(platform_counts)}")

        if inp.trend_reports:
            all_trends = []
            for p, r in inp.trend_reports.items():
                items = r.get("items", []) if isinstance(r, dict) else []
                all_trends.extend(it.get("title", "")[:40] for it in items[:3])
            if all_trends:
                context_parts.append(f"趋势信号: {'; '.join(all_trends[:5])}")

        if inp.product_report:
            products = inp.product_report.get("items", []) if isinstance(inp.product_report, dict) else []
            names = [p.get("name", "")[:30] for p in products[:5]]
            if names:
                context_parts.append(f"选品: {', '.join(names)}")

        # 按 mode 篩選示例
        mode_examples_good = [ex for ex in self._FEWSHOT_GOOD if ex["mode"] == inp.mode]
        good_examples_text = "\n".join(
            f"  ✅ [{ex['mode']}] {ex.get('topic', '')}\n     {json.dumps(ex['output'], ensure_ascii=False)[:300]}"
            for ex in mode_examples_good
        )
        mode_examples_bad = [ex for ex in self._FEWSHOT_BAD if ex["mode"] == inp.mode]
        if not mode_examples_bad:
            mode_examples_bad = self._FEWSHOT_BAD  # fallback: show both
        bad_examples_text = "\n".join(
            f"  ❌ [{ex['mode']}]\n     {ex['why_bad']}"
            for ex in mode_examples_bad
        )

        prompt = f"""你是頂級內容策略分析師（Content Remixer），專精於數據總結、賽道分析和跨平台內容改寫。

## 任務
當前模式: **{inp.mode}**。請根據模式執行對應的任務。

## 品質標準
- 好的分析：有具體數據和百分比、競爭判斷有依據、建議可執行、改寫體現平台差異
- 差的分析：空泛結論無數據支撐、競爭分析永遠說「中等」、建議如「做內容」「做行銷」等不可執行、改寫僅改emoji

## 競爭分析維度定義（analyze 模式重要參考）
- **competition_level（競爭程度）**
  - 高：頭部 3-5 個玩家佔據 60%+ 內容曝光/市場份額，新入場者難以獲得自然流量
  - 中：有明顯頭部但長尾活躍（頭部<40%），新入場者仍可透過差異化獲得流量
  - 低：無明顯頭部，內容供不應求，早期入場者有先發優勢
- **entry_barrier（進入門檻）**：必須具體描述所需資源/能力（資金量級/技術要求/供應鏈/人才/牌照等），禁用「一定資金」「一些技術」等模糊表述

## Few-Shot 正例（{inp.mode} 模式專屬示例）
{good_examples_text}

## Few-Shot 負例（避免以下錯誤）
{bad_examples_text}

## 邊界情況處理
- 數據量 <5 條：在 summary 明確標註「數據量不足以進行可靠分析，以下結論僅供參考」
- 跨模式請求：嚴格按當前 {inp.mode} 模式處理
- 多平台數據合併：platform_breakdown 用實際數據，不得憑空編造

## 背景數據
{chr(10).join(context_parts)}"""

        try:
            output = await self._call_llm_with_critic(prompt, RemixOutput, "content_remixer", temperature=0.5, max_tokens=4000)

            insights = [
                TrackInsight(
                    topic=t.topic,
                    competition_level=t.competition_level,
                    entry_barrier=t.entry_barrier,
                    opportunity_score=t.opportunity_score,
                    recommended_angles=t.recommended_angles,
                )
                for t in output.track_insights
            ]

            rewrites = [
                ContentRewrite(
                    original=r.original,
                    source_platform=r.source_platform,
                    target_platform=r.target_platform,
                    rewritten=r.rewritten,
                    changes_summary=r.changes_summary,
                )
                for r in output.rewrites
            ]

            return RemixReport(
                topic=inp.topic or "通用",
                mode=inp.mode,
                summary=output.summary,
                key_keywords=output.key_keywords,
                platform_breakdown=output.platform_breakdown or dict(platform_counts),
                track_insights=insights,
                rewrites=rewrites,
                recommendations=output.recommendations,
            )
        except Exception as exc:
            logger.warning(f"ContentRemixer LLM 失败: {exc}")
            return self._fallback(inp)

    def _fallback(self, inp: RemixInput) -> RemixReport:
        platform_counts = dict(Counter(
            it.get("platform", "unknown") for it in inp.raw_items
        ))
        titles = [it.get("title", "") for it in inp.raw_items[:20]]

        keywords: list[str] = []
        if titles:
            words = []
            for t in titles:
                words.extend(w for w in t[:30].replace(" ", "").replace("，", ",").split(",") if len(w) >= 2)
            keywords = [w for w, _ in Counter(words).most_common(5)]

        total = sum(platform_counts.values())

        if inp.mode == "summarize":
            top_platform = max(platform_counts, key=platform_counts.get) if platform_counts else "未知"
            return RemixReport(
                topic=inp.topic or "通用",
                mode="summarize",
                summary=f"共采集 {total} 条内容，{top_platform} 占比最高",
                key_keywords=keywords,
                platform_breakdown=platform_counts,
            )

        if inp.mode == "analyze":
            return RemixReport(
                topic=inp.topic or "通用",
                mode="analyze",
                summary=f"基于 {total} 条数据的基础统计（需 LLM 深度分析）",
                key_keywords=keywords,
                platform_breakdown=platform_counts,
                track_insights=[
                    TrackInsight(
                        topic=inp.topic or "通用",
                        competition_level="中",
                        entry_barrier="需 LLM 分析",
                        opportunity_score=50,
                        recommended_angles="建议开启 DeepSeek API 获取深度分析",
                    )
                ],
                recommendations="LLM 不可用，降级为模板分析",
            )

        if inp.mode == "rewrite":
            fallback_rewrites = []
            _REWRITE_TEMPLATES = {
                ("douyin", "xiaohongshu"): ("✨{t}\n#好物分享 #干货",
                    "加emoji前缀+话题标签"),
                ("xiaohongshu", "bilibili"): ("【深度】{t}｜全方位解析",
                    "加【】前缀+深度标题"),
                ("bilibili", "douyin"): ("{t}，绝了！",
                    "缩短+口语化"),
            }
            for item in inp.raw_items[:3]:
                t = item.get("title", "")
                if not t:
                    continue
                src = item.get("platform", "douyin")
                for (s, d), (tmpl, reason) in _REWRITE_TEMPLATES.items():
                    if s == src:
                        fallback_rewrites.append(ContentRewrite(
                            original=t, source_platform=s,
                            target_platform=d,
                            rewritten=tmpl.format(t=t[:40]),
                            changes_summary=f"模板: {reason}",
                        ))

            return RemixReport(
                topic=inp.topic or "通用",
                mode="rewrite",
                summary=f"基于 {len(fallback_rewrites)} 条内容的模板改写（需 LLM 深度改写）",
                rewrites=fallback_rewrites,
                recommendations="LLM 不可用，降级为模板改写",
            )

        return RemixReport(topic=inp.topic or "通用", mode=inp.mode, summary="未知模式")
