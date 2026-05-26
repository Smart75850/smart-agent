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

import httpx

from config.settings import settings
from src.utils.logger import logger


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


class ContentRemixer:
    """数据分析/总结/改写 Agent。"""

    def __init__(self):
        self._api_key = settings.DEEPSEEK_API_KEY or settings.LLM_API_KEY
        self._api_url = settings.DEEPSEEK_API_URL or settings.LLM_API_URL or "https://api.deepseek.com/v1"
        self._model = settings.DEEPSEEK_MODEL or settings.LLM_MODEL or "deepseek-chat"

    async def run(self, inp: RemixInput) -> RemixReport:
        if not self._api_key:
            return self._fallback(inp)

        return await self._llm_generate(inp)

    async def as_node(self, state: dict) -> dict:
        merged = state.get("merged_items", [])
        scored = state.get("scored_items", [])
        raw_items = scored if scored else merged

        report = await self.run(RemixInput(
            mode="summarize",
            topic=state.get("keyword", ""),
            raw_items=raw_items,
            trend_reports=state.get("trend_reports", {}),
            product_report=state.get("product_report", {}),
            video_report=state.get("video_report", {}),
            sentiment_report=state.get("sentiment_report", {}),
        ))

        return {"remix_report": asdict(report)}

    async def _llm_generate(self, inp: RemixInput) -> RemixReport:
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

        mode_prompts = {
            "summarize": (
                f'{{"summary": "一句话摘要", "key_keywords": ["词1","词2","词3"], '
                f'"platform_breakdown": {{"bilibili": 5, "douyin": 3}}}}'
            ),
            "analyze": (
                f'{{"summary": "赛道总结", '
                f'"track_insights": [{{"topic": "赛道名", "competition_level": "高/中/低", '
                f'"entry_barrier": "门槛描述", "opportunity_score": 0-100, '
                f'"recommended_angles": "建议切入角度"}}], '
                f'"recommendations": "策略建议一句话"}}'
            ),
            "rewrite": (
                f'{{"summary": "改写说明", '
                f'"rewrites": [{{"original": "原标题", "source_platform": "douyin", '
                f'"target_platform": "xiaohongshu", "rewritten": "改写后内容", '
                f'"changes_summary": "改动说明"}}]}}'
            ),
        }

        prompt = (
            f"你是一个内容策略分析助手。模式: {inp.mode}。\n\n"
            + "\n".join(context_parts)
            + f"\n\n请返回 JSON（不要 markdown 代码块）：\n"
            + mode_prompts.get(inp.mode, mode_prompts["summarize"])
        )

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self._api_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.5,
                        "max_tokens": 2000,
                    },
                )
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)

                insights = [
                    TrackInsight(
                        topic=t.get("topic", ""),
                        competition_level=t.get("competition_level", ""),
                        entry_barrier=t.get("entry_barrier", ""),
                        opportunity_score=int(t.get("opportunity_score", 50)),
                        recommended_angles=t.get("recommended_angles", ""),
                    )
                    for t in parsed.get("track_insights", [])
                ]

                rewrites = [
                    ContentRewrite(
                        original=r.get("original", ""),
                        source_platform=r.get("source_platform", ""),
                        target_platform=r.get("target_platform", ""),
                        rewritten=r.get("rewritten", ""),
                        changes_summary=r.get("changes_summary", ""),
                    )
                    for r in parsed.get("rewrites", [])
                ]

                return RemixReport(
                    topic=inp.topic or "通用",
                    mode=inp.mode,
                    summary=parsed.get("summary", ""),
                    key_keywords=parsed.get("key_keywords", []),
                    platform_breakdown=parsed.get("platform_breakdown", dict(platform_counts)),
                    track_insights=insights,
                    rewrites=rewrites,
                    recommendations=parsed.get("recommendations", ""),
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
            from collections import Counter as C
            words = []
            for t in titles:
                words.extend(w for w in t[:30].replace(" ", "").replace("，", ",").split(",") if len(w) >= 2)
            keywords = [w for w, _ in C(words).most_common(5)]

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
                    if s == src or not src:
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
