"""Content Remixer Agent — 数据分析/总结/改写。

CopyWriter = 原创生成，Remixer = 改写成文。

Mode:
  summarize — 数据总结（摘要 + 关键词 + 平台分布）
  analyze   — 赛道分析（竞争格局 + 内容策略 + 风险提示）
  rewrite   — 跨平台改写（抖音↔小红书↔B站）

用法:
  remixer = ContentRemixer()
  report = await remixer.run(RemixInput(mode="summarize", topic="AI", raw_items=[...]))
"""

import json
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import Literal

from pydantic import BaseModel, Field

from src.orchestrator.agents.base import BaseAgent
from src.utils.logger import logger


# ── 模式專用 Pydantic 輸出模型（拆成 3 個輕量 Schema）─────

class SummarizeOutput(BaseModel):
    summary: str = Field(min_length=30, description="数据总结，含核心发现+平台分布特点")
    key_keywords: list[str] = Field(min_length=3, max_length=8, description="3-8个关键词")
    platform_breakdown: dict[str, int] = Field(description="平台→内容数量")


class TrackInsightOutput(BaseModel):
    topic: str = Field(description="细分赛道名")
    competition_level: Literal["高", "中", "低"] = Field(description="竞争程度")
    entry_barrier: str = Field(min_length=30, description="具体门槛，含资金/技术/资源量化描述")
    opportunity_score: int = Field(ge=0, le=100, description="机会评分")
    recommended_angles: str = Field(min_length=40, description="2-3个具体切入角度，含目标人群+差异化+执行路径")


class AnalyzeOutput(BaseModel):
    summary: str = Field(min_length=60, description="竞争格局总结，含头部集中度+机会窗口+风险提示")
    track_insights: list[TrackInsightOutput] = Field(min_length=1, max_length=5, description="1-5个细分赛道洞察")
    key_keywords: list[str] = Field(min_length=3, max_length=8, description="3-8个关键词")
    recommendations: str = Field(min_length=40, description="策略建议，含优先级+资源需求+执行路径")
    platform_breakdown: dict[str, int] = Field(default_factory=dict, description="平台分布")


class ContentRewriteOutput(BaseModel):
    original: str = Field(description="原内容标题/文案")
    source_platform: Literal["douyin", "xiaohongshu", "bilibili", "zhihu", "kuaishou", "weibo", "tieba"] = Field(description="来源平台")
    target_platform: Literal["douyin", "xiaohongshu", "bilibili", "zhihu", "kuaishou", "weibo", "tieba"] = Field(description="目标平台")
    rewritten: str = Field(min_length=30, description="改写后内容")
    changes_summary: str = Field(min_length=30, description="改动说明，含语言/节奏/信息密度/情绪四个维度的变化")


class RewriteOutput(BaseModel):
    summary: str = Field(min_length=30, description="改写策略说明")
    rewrites: list[ContentRewriteOutput] = Field(min_length=1, max_length=5, description="改写结果列表")


# ── Dataclass 層 ───────────────────────────────────────────

@dataclass
class RemixInput:
    mode: str = "summarize"
    topic: str = ""
    raw_items: list = field(default_factory=list)
    trend_reports: dict = field(default_factory=dict)
    product_report: dict = field(default_factory=dict)
    video_report: dict = field(default_factory=dict)
    sentiment_report: dict = field(default_factory=dict)


@dataclass
class TrackInsight:
    topic: str = ""
    competition_level: str = ""
    entry_barrier: str = ""
    opportunity_score: int = 0
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

        if inp.mode == "summarize":
            return await self._generate_summarize(inp)
        elif inp.mode == "analyze":
            return await self._generate_analyze(inp)
        elif inp.mode == "rewrite":
            return await self._generate_rewrite(inp)
        else:
            return RemixReport(topic=inp.topic, mode=inp.mode, summary=f"未知模式: {inp.mode}")

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

    # ── Few-Shot 示例庫 ──────────────────────────────────────

    _SUMMARIZE_FEWSHOT = [
        {"topic": "AI绘图工具",
         "output": {"summary": "AI绘图赛道正从'能出图'转向'精准可控'，Midjourney主导艺术方向而Stable Diffusion在商用API侧增长最快，20条内容中12条讨论可控性问题",
                    "key_keywords": ["AI绘图", "Midjourney", "Stable Diffusion", "可控生成", "商用API"],
                    "platform_breakdown": {"bilibili": 8, "xiaohongshu": 6, "douyin": 4, "zhihu": 2}}},
        {"topic": "居家健身",
         "output": {"summary": "居家健身内容在春节后出现明显高峰，核心话题从'减肥'转向'体态矫正'，瑜伽垫和弹力带是最常出现的关联商品",
                    "key_keywords": ["居家健身", "体态矫正", "瑜伽", "弹力带", "无器械训练"],
                    "platform_breakdown": {"douyin": 12, "xiaohongshu": 5, "bilibili": 3}}},
    ]

    _ANALYZE_FEWSHOT = [
        {"topic": "蓝牙耳机",
         "output": {"summary": "蓝牙耳机赛道头部集中度高但中腰部仍有细分机会。头部3个品牌占65%内容曝光，但'降噪''运动''低延迟'三个垂直方向各有10-15%长尾创作者活跃。最大机会在'百元内性价比'细分",
                    "track_insights": [{"topic": "蓝牙耳机-降噪", "competition_level": "高", "entry_barrier": "需ANC技术储备+声学调校经验，头部品牌专利壁垒明显",
                                       "opportunity_score": 35, "recommended_angles": "避开ANC主战场，切入'通话降噪'细分——技术门槛低+远程办公需求大"}],
                    "key_keywords": ["蓝牙耳机", "降噪", "性价比", "运动耳机"],
                    "recommendations": "建议从百元价位段切入，主打通话降噪+超长续航",
                    "platform_breakdown": {"douyin": 15, "bilibili": 8, "xiaohongshu": 5}}},
        {"topic": "新中式穿搭",
         "output": {"summary": "新中式穿搭处于爆发前夜：搜索量月增长200%+，但目前专业创作者少，内容供不应求。天猫数据显示相关商品GMV同比+340%",
                    "track_insights": [{"topic": "新中式穿搭-日常款", "competition_level": "低", "entry_barrier": "需对传统服饰文化有理解（非硬门槛）+ 供应链（可从档口拿货起步）+ 视觉审美能力",
                                       "opportunity_score": 93, "recommended_angles": "1) 新中式通勤穿搭 2) 平价新中式（打破'贵'的认知）3) 微胖/小个子新中式（人群精准）"}],
                    "key_keywords": ["新中式", "穿搭", "国风", "通勤", "平价"],
                    "recommendations": "黄金窗口期6-12个月，建议快速起号抢占'新中式通勤'内容真空",
                    "platform_breakdown": {"xiaohongshu": 18, "douyin": 10}}},
    ]

    _REWRITE_FEWSHOT = [
        {"output": {"summary": "抖音→小红书：降节奏+加emoji+软化语气+增加场景描述",
                    "rewrites": [{"original": "3个信号告诉你房价要跌了", "source_platform": "douyin", "target_platform": "xiaohongshu",
                                  "rewritten": "🏠 注意！这3个信号出现，说明房价可能要变天了\n最近多地楼市出现异动，我整理了3个关键指标…",
                                  "changes_summary": "从快节奏警告风→小红书精致资讯风：加emoji、语气从'告诉你'变为'说明'、增加上下文铺垫"}]}},
        {"output": {"summary": "小红书→B站：增加信息密度+数据背书+深度框架",
                    "rewrites": [{"original": "✨挖到宝了！这个小众香薰好闻到犯规", "source_platform": "xiaohongshu", "target_platform": "bilibili",
                                  "rewritten": "【深度测评】我买了市面上12款小众香薰，用气相色谱仪测出了最好闻的一款",
                                  "changes_summary": "从小红书感性分享→B站硬核测评：去掉emoji、增加数据维度（12款/仪器）、建立专业人设"}]}},
    ]

    # ── 模式專用生成方法 ────────────────────────────────────

    async def _generate_summarize(self, inp: RemixInput) -> RemixReport:
        """总结模式 — 轻量 prompt，不走 Critic。"""
        context = self._build_context(inp)
        fewshot_text = "\n".join(
            f"  ✅ {ex['topic']}: {json.dumps(ex['output'], ensure_ascii=False)[:250]}"
            for ex in self._SUMMARIZE_FEWSHOT
        )

        prompt = f"""你是数据分析师。总结以下内容数据，返回 JSON。

规则：
1. summary 含核心发现+平台分布特点（30字以上）
2. key_keywords 3-8个，按频率排序
3. platform_breakdown 用实际数据，不得编造
4. 数据量<5条时在summary标注「数据量不足」

示例：
{fewshot_text}

数据：
{chr(10).join(context)}"""

        try:
            output = await self._call_llm(prompt, temperature=0.3, max_tokens=800, json_mode=True)
            parsed = self._parse_json(output)
            return RemixReport(
                topic=inp.topic or "通用",
                mode="summarize",
                summary=parsed.get("summary", ""),
                key_keywords=parsed.get("key_keywords", []),
                platform_breakdown=parsed.get("platform_breakdown", {}),
            )
        except Exception as exc:
            logger.warning(f"ContentRemixer summarize 失败: {exc}")
            return self._fallback(inp)

    async def _generate_analyze(self, inp: RemixInput) -> RemixReport:
        """分析模式 — 用 Critic 保證品質。"""
        context = self._build_context(inp)
        fewshot_text = "\n".join(
            f"  ✅ {ex['topic']}: {json.dumps(ex['output'], ensure_ascii=False)[:300]}"
            for ex in self._ANALYZE_FEWSHOT
        )

        prompt = f"""你是赛道分析专家。分析以下内容数据，返回 JSON。

规则：
1. summary 含头部集中度+机会窗口+风险提示（60字以上）
2. track_insights 1-5个细分赛道，每个必须有：
   - competition_level: 高(头部60%+)/中(头部<40%)/低(无明显头部)
   - entry_barrier: 具体量化（资金量级/技术/供应链），禁用模糊词
   - opportunity_score: 90+=蓝海 70-89=可突围 50-69=红海 <50=不建议
   - recommended_angles: 2-3个具体切入角度，含目标人群+差异化点+执行路径（40字以上）
3. recommendations: 策略建议，含优先级+资源需求（40字以上）
4. 数据量<5条时在summary标注「数据量不足」

示例：
{fewshot_text}

数据：
{chr(10).join(context)}"""

        try:
            output = await self._call_llm_with_critic(
                prompt, AnalyzeOutput, "content_remixer_analyze",
                temperature=0.4, max_tokens=4000
            )
            insights = [
                TrackInsight(topic=t.topic, competition_level=t.competition_level,
                             entry_barrier=t.entry_barrier, opportunity_score=t.opportunity_score,
                             recommended_angles=t.recommended_angles)
                for t in output.track_insights
            ]
            return RemixReport(
                topic=inp.topic or "通用", mode="analyze",
                summary=output.summary, key_keywords=output.key_keywords,
                platform_breakdown=output.platform_breakdown,
                track_insights=insights, recommendations=output.recommendations,
            )
        except Exception as exc:
            logger.warning(f"ContentRemixer analyze 失败: {exc}")
            return self._fallback(inp)

    async def _generate_rewrite(self, inp: RemixInput) -> RemixReport:
        """改写模式 — 用 Critic 保證品質。"""
        titles = [it.get("title", "")[:50] for it in (inp.raw_items or [])[:5]]
        if not titles:
            return RemixReport(topic=inp.topic, mode="rewrite", summary="无内容可改写")

        fewshot_text = "\n".join(
            f"  ✅ {json.dumps(ex['output'], ensure_ascii=False)[:300]}"
            for ex in self._REWRITE_FEWSHOT
        )

        items_text = "\n".join(f"{i}. [{it.get('platform', 'douyin')}] {it.get('title', '')[:60]}"
                               for i, it in enumerate((inp.raw_items or [])[:5]))

        prompt = f"""你是跨平台内容改写专家。将以下内容改写为目标平台风格，返回 JSON。

规则：
1. 改写体现代平台差异：语言习惯、信息密度、情绪基调
2. changes_summary 含语言/节奏/信息密度/情绪四个维度的变化（30字以上）
3. 不只是加emoji——要重构表达方式
4. 目标平台为输入内容平台之外的其他平台

示例：
{fewshot_text}

待改写内容：
{items_text}"""

        try:
            output = await self._call_llm_with_critic(
                prompt, RewriteOutput, "content_remixer_rewrite",
                temperature=0.5, max_tokens=3000
            )
            rewrites = [
                ContentRewrite(original=r.original, source_platform=r.source_platform,
                               target_platform=r.target_platform, rewritten=r.rewritten,
                               changes_summary=r.changes_summary)
                for r in output.rewrites
            ]
            return RemixReport(
                topic=inp.topic or "通用", mode="rewrite",
                summary=output.summary, rewrites=rewrites,
            )
        except Exception as exc:
            logger.warning(f"ContentRemixer rewrite 失败: {exc}")
            return self._fallback(inp)

    def _build_context(self, inp: RemixInput) -> list[str]:
        """构建统一的数据上下文。"""
        context_parts = [f"主题: {inp.topic or '通用'}"]
        if inp.raw_items:
            titles = [it.get("title", "")[:50] for it in inp.raw_items[:10]]
            context_parts.append(f"原始内容({len(inp.raw_items)}条): {'; '.join(titles)}")
        platform_counts = Counter(it.get("platform", "unknown") for it in inp.raw_items)
        context_parts.append(f"平台分布: {dict(platform_counts)}")
        total = sum(platform_counts.values())
        if total < 5:
            context_parts.append("⚠️ 数据量不足5条，结论仅供参考")
        return context_parts

    def _fallback(self, inp: RemixInput) -> RemixReport:
        platform_counts = dict(Counter(it.get("platform", "unknown") for it in inp.raw_items))
        titles = [it.get("title", "") for it in inp.raw_items[:20]]

        keywords: list[str] = []
        if titles:
            words = []
            for t in titles:
                words.extend(w for w in t[:30].replace(" ", "").replace("，", ",").split(",") if len(w) >= 2)
            keywords = [w for w, _ in Counter(words).most_common(5)]

        total = sum(platform_counts.values())
        top_platform = max(platform_counts, key=platform_counts.get) if platform_counts else "未知"

        if inp.mode == "summarize":
            return RemixReport(topic=inp.topic or "通用", mode="summarize",
                summary=f"共采集 {total} 条内容，{top_platform} 占比最高",
                key_keywords=keywords, platform_breakdown=platform_counts)

        if inp.mode == "analyze":
            return RemixReport(topic=inp.topic or "通用", mode="analyze",
                summary=f"基于 {total} 条数据的基础统计（需 LLM 深度分析）",
                key_keywords=keywords, platform_breakdown=platform_counts)

        if inp.mode == "rewrite":
            _REWRITE_TEMPLATES = {
                ("douyin", "xiaohongshu"): ("✨{t}\n#好物分享 #干货", "加emoji+话题标签"),
                ("xiaohongshu", "bilibili"): ("【深度】{t}｜全方位解析", "加【】前缀+深度标题"),
                ("bilibili", "douyin"): ("{t}，绝了！", "缩短+口语化"),
            }
            fallback_rewrites = []
            for item in inp.raw_items[:3]:
                t = item.get("title", "")
                if not t: continue
                src = item.get("platform", "douyin")
                for (s, d), (tmpl, reason) in _REWRITE_TEMPLATES.items():
                    if s == src:
                        fallback_rewrites.append(ContentRewrite(
                            original=t, source_platform=s, target_platform=d,
                            rewritten=tmpl.format(t=t[:40]), changes_summary=f"模板: {reason}",
                        ))
            return RemixReport(topic=inp.topic or "通用", mode="rewrite",
                summary=f"基于 {len(fallback_rewrites)} 条内容的模板改写（需 LLM 深度改写）",
                rewrites=fallback_rewrites)

        return RemixReport(topic=inp.topic or "通用", mode=inp.mode, summary="未知模式")
