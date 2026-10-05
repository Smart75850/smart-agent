from __future__ import annotations
"""Trend Scout Agent — 爆款趋势分析。

Flow:
  1. 采集目标平台 hot/search 数据
  2. DeepSeek V4 Flash 分析爆款规律
  3. 输出爆款候选列表 (viral_score + trend_reason)

用法:
  scout = TrendScout()
  report = await scout.run(platform="bilibili", keyword="AI")  # search 模式
  report = await scout.run(platform="bilibili")                 # hot 模式
  # LangGraph node: scout.as_node()
"""

import asyncio
import json
from dataclasses import dataclass, field, asdict

from typing import Literal
from pydantic import BaseModel, Field, field_validator

from src.orchestrator.agents.base import BaseAgent
from src.utils.logger import logger


# ── 分类别名映射（LLM 常见变体 → 标准枚举值）─────────────

_CATEGORY_ALIASES: dict[str, str] = {
    # 常见变体 → 标准简体枚举值
    "财经": "财经", "游戏": "游戏", "娱乐": "娱乐",
    "旅游": "旅游", "母婴": "母婴", "宠物": "宠物", "健康": "健康/医疗",
    "医疗": "健康/医疗", "健身运动": "健身",
    # 繁体输入兼容：prompt 与枚举值已统一为简体（2026-10-06），
    # 但 LLM 偶尔仍可能输出繁体，故保留一层映射兜底
    "美妝": "美妆", "財經": "财经", "遊戲": "游戏", "娛樂": "娱乐",
    "旅遊": "旅游", "母嬰": "母婴", "寵物": "宠物", "醫療": "健康/医疗",
    "數碼": "科技/AI", "學習": "教育", "游戲": "游戏",
    # 科技/数码相关
    "数码": "科技/AI", "科技": "科技/AI",
    "AI": "科技/AI", "人工智能": "科技/AI", "AI工具": "科技/AI",
    # 教育相关
    "学习": "教育", "考试": "教育",
    # 家居相关
    "房产": "家居", "装修": "家居", "房地产": "家居",
    # 财经相关
    "金融": "财经", "投资": "财经", "理财": "财经",
    # 其他常见输出
    "搞笑": "娱乐", "综艺": "娱乐", "明星": "娱乐",
    "汽车": "其他", "职场": "其他",
}

_CATEGORY_VALUES = frozenset([
    "科技/AI", "美妆", "美食", "穿搭", "家居", "健身", "教育",
    "财经", "游戏", "娱乐", "旅游", "母婴", "宠物", "健康/医疗", "其他",
])


# ── Pydantic 结构化输出模型 ─────────────────────────────────

class TrendScoutItemOutput(BaseModel):
    index: int = Field(description="内容在输入列表中的索引")
    viral_score: int = Field(ge=0, le=100, description="爆款潜力分：90+蓝海/70-89有需求/50-69红海/<50小众")
    # M1 fix：trend_reason 改 default "" 避免 pydantic 拒绝整个 output
    # （LLM 偶尔返 items 截断，缺 trend_reason 字段）
    trend_reason: str = Field(default="", description="爆款原因分析，引用具体数据+爆款机制（可空，graceful）")
    category: str = Field(default="其他", description="分类枚举（15 类之一，默认其他）")
    growth_velocity: Literal["exploding", "rising", "stable", "declining"] = Field(default="stable", description="增长速度：exploding(互动比>5%+新赛道)/rising(3-5%)/stable(1-3%)/declining(<1%)")
    trend_lifecycle: Literal["early", "peak", "mature", "declining"] = Field(default="peak", description="生命周期：early(新赛道少竞品)/peak(爆发期竞品涌现)/mature(稳定饱和)/declining(互动下滑)")

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, v: str) -> str:
        """将 LLM 常见变体映射到标准枚举值，做繁简兼容。"""
        if v in _CATEGORY_VALUES:
            return v
        mapped = _CATEGORY_ALIASES.get(v)
        if mapped:
            return mapped
        # 模糊匹配：去掉空格后重试
        stripped = v.replace(" ", "")
        if stripped in _CATEGORY_VALUES:
            return stripped
        mapped2 = _CATEGORY_ALIASES.get(stripped)
        if mapped2:
            return mapped2
        # 最后兜底：包含关键词的映射
        for alias, target in _CATEGORY_ALIASES.items():
            if alias in v or v in alias:
                return target
        return v


class TrendScoutOutput(BaseModel):
    summary: str = Field(min_length=30, description="整体趋势一句话，含赛道判断+机会信号")
    items: list[TrendScoutItemOutput] = Field(description="爆款候选列表")


@dataclass
class TrendItem:
    title: str
    platform: str
    viral_score: int          # 0-100 爆款潛力分
    trend_reason: str         # 爆款原因分析
    category: str = ""        # 品類
    growth_velocity: str = "" # exploding/rising/stable/declining
    trend_lifecycle: str = "" # early/peak/mature/declining
    engagement: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


@dataclass
class TrendReport:
    platform: str
    keyword: str
    total_candidates: int
    items: list[TrendItem] = field(default_factory=list)
    summary: str = ""


class TrendScout(BaseAgent):
    """爆款趨勢分析 Agent。"""

    # ── public API ────────────────────────────────────────────

    async def run(
        self,
        platform: str = "bilibili",
        keyword: str = "",
        limit: int = 20,
        items: list[dict] | None = None,
    ) -> TrendReport:
        """主入口：採集 + 分析，返回 TrendReport。

        items 参数可选 — 如果提供则直接使用（跳过 _collect），
        用于 Pipeline 中复用已搜索数据避免 CDP 重搜超时。
        """
        if items is None:
            items = await self._collect(platform, keyword, limit)
        if not items:
            logger.warning(f"TrendScout: [{platform}] 无数据，跳过分析")
            return TrendReport(platform=platform, keyword=keyword, total_candidates=0)

        report = await self._llm_generate(platform, keyword, items)
        logger.info(
            f"TrendScout: [{platform}] {report.total_candidates} 个爆款候选"
        )
        return report

    async def as_node(self, state: dict) -> dict:
        """LangGraph 節點接口 — 优先用 merged_items 避免重搜。"""
        keyword = state.get("keyword", "")
        platforms = state.get("platforms", ["bilibili"])
        merged = state.get("merged_items", [])

        all_reports = {}
        for p in platforms:
            # 从 pipeline 已搜索数据中提取该平台条目
            plat_items = [it for it in merged if it.get("platform") == p]
            if plat_items:
                report = await self.run(platform=p, keyword=keyword, items=plat_items, limit=state.get("limit", 20))
            else:
                report = await self.run(platform=p, keyword=keyword, limit=state.get("limit", 20))
            all_reports[p] = asdict(report)

        return {"trend_reports": all_reports}

    # ── internal ──────────────────────────────────────────────

    async def _collect(self, platform: str, keyword: str, limit: int) -> list[dict]:
        """採集平台數據 (hot 或 search)。"""
        from src.orchestrator.nodes import _get_adapter, _retry

        adapter = _get_adapter(platform)
        try:
            if keyword:
                raw = await _retry(lambda: adapter.search(keyword, limit=limit))
            else:
                raw = await _retry(lambda: adapter.hot(limit=limit))
        except Exception as exc:
            logger.warning(f"TrendScout _collect [{platform}]: {exc}")
            return []

        from src.aggregator import _normalize
        return [_normalize(item, platform) for item in (raw if isinstance(raw, list) else [])]

    # ── Few-Shot 示例庫 ──────────────────────────────────────
    _FEWSHOT_GOOD = [
        # L2 fix：few-shot 从 5+2 缩到 2+1（节省 ~400 tokens 装 actual JSON output）
        {"title": "我用AI做了一个能自动回复客服的机器人，成本只花了50块", "plays": "85万", "likes": "4.2万",
         "viral_score": 92, "category": "科技/AI",
         "trend_reason": "AI工具实操+极低成本+个人即商用，互动比4.9%远超均值，蓝海信号明确"},
        {"title": "小个子女生这样穿显高10cm！5套通勤穿搭公式", "plays": "120万", "likes": "6.8万",
         "viral_score": 85, "category": "穿搭",
         "trend_reason": "精准人群+数字冲击+公式化教程，互动比5.7%"},
    ]

    _FEWSHOT_BAD = [
        {"title": "今天的天气真好呀阳光明媚", "plays": "1.2万", "likes": "200",
         "viral_score": 8, "category": "其他",
         "trend_reason": "❌ 纯个人生活记录、无爆款元素、互动比仅1.7%"},
    ]

    async def _llm_generate(
        self, platform: str, keyword: str, items: list[dict]
    ) -> TrendReport:
        """DeepSeek LLM 分析爆款趨勢（v2 增強 prompt）。"""
        if not self._api_key:
            logger.info("LLM 未配置，使用纯热度排序")
            return self._fallback(platform, keyword, items)

        # M2 fix：减少 max items from 15 → 5（避免 LLM 截断导致 validation fail）
        items_text = "\n".join(
            f"{i}. {it.get('title','')} | 播放:{it.get('plays','0')} | 赞:{it.get('likes','0')} | 作者:{it.get('author','')}"
            for i, it in enumerate(items[:5])
        )

        good_examples_text = "\n".join(
            f"  ✅ [{ex['category']}] score={ex['viral_score']} | {ex['title'][:50]}\n     → {ex['trend_reason']}"
            for ex in self._FEWSHOT_GOOD
        )
        bad_examples_text = "\n".join(
            f"  ❌ [{ex['category']}] score={ex['viral_score']} | {ex['title'][:50]}\n     → {ex['trend_reason']}"
            for ex in self._FEWSHOT_BAD
        )

        context = f"平台: {platform}" + (f", 关键词: {keyword}" if keyword else " (热榜)")
        prompt = f"""<role>
你是爆款趋势分析师（Trend Scout）。你的唯一职责：Analyze 社交媒体内容列表，Score 每条内容的爆款潜力，Classify 赛道分类，Extract 可复制的爆款机制。
</role>

<scope>
OWN: 内容趋势识别、爆款评分、赛道分类
BOUNDARY: 不生成文案（那是 CopyWriter 的职责）、不分析视频结构（那是 VideoAnalyst 的职责）、不评估商品变现（那是 ProductMiner 的职责）
ESCALATE: 数据全部为0时 → 返回空分析并标注原因；连续3条以上无爆款信号 → 在 summary 中明确声明
</scope>

<quality_standards>
1. trend_reason 引用至少1个数据点（播放量/互动比/增长率）
2. viral_score 体现鉴别度（最高最低分差 ≥20），类似时 summary 说明
3. category 精确枚举（15类之一）
4. summary 包含：主导赛道 + 机会信号 + 风险提示
</quality_standards>

<viral_rules>
爆款（4项≥2）：互动比>3% / 热门赛道 / 标题含情绪词 / 形式创新
评分：>90 蓝海 / 70-89 需求 / 50-69 红海 / <50 小众
</viral_rules>

<category_enum>15 类：科技/AI | 美妆 | 美食 | 穿搭 | 家居 | 健身 | 教育 | 财经 | 游戏 | 娱乐 | 旅游 | 母婴 | 宠物 | 健康/医疗 | 其他</category_enum>

<examples>
{good_examples_text}
{bad_examples_text}
</examples>

<prediction>
每条内容标注：
- growth_velocity: exploding / rising / stable / declining
- trend_lifecycle: early / peak / mature / declining
</prediction>

<edge_cases>数据缺失 viral_score≤50 + declining；广告内容 扣20分；跨类别选主类别</edge_cases>

<task>
平台: {platform} | 关键词: {keyword}
{items_text}
</task>"""

        try:
            output = await self._call_llm_with_critic(prompt, TrendScoutOutput, "trend_scout", temperature=0.3)

            # M2 fix：partial items handling（LLM 截断 → 接受 valid 部分，skip invalid）
            trend_items = []
            for ti in output.items:
                try:
                    idx = ti.index
                    src = items[idx] if 0 <= idx < len(items) else {}
                    trend_items.append(TrendItem(
                        title=src.get("title", ""),
                        platform=platform,
                        viral_score=ti.viral_score,
                        trend_reason=ti.trend_reason or "（LLM 未生成详细理由）",
                        category=ti.category if ti.category in _CATEGORY_VALUES else "其他",
                        growth_velocity=getattr(ti, 'growth_velocity', 'stable'),
                        trend_lifecycle=getattr(ti, 'trend_lifecycle', 'peak'),
                        engagement={"plays": src.get("plays", "0"), "likes": src.get("likes", "0")},
                        raw=src,
                    ))
                except Exception as item_exc:
                    # Skip individual bad item
                    logger.warning(f"TrendScout skip bad item idx={ti.index}: {item_exc}")
                    continue

            trend_items.sort(key=lambda x: x.viral_score, reverse=True)
            return TrendReport(
                platform=platform,
                keyword=keyword or "hot",
                total_candidates=len(trend_items),
                items=trend_items,
                summary=output.summary,
            )

        except Exception as exc:
            logger.warning(f"TrendScout LLM 失败，降级为热度排序: {exc}")
            return self._fallback(platform, keyword, items)

    def _fallback(self, platform: str, keyword: str, items: list[dict]) -> TrendReport:
        """降級模式: 純熱度排序。"""
        def _parse_count(value) -> int:
            s = str(value or 0).replace(",", "").strip()
            if not s:
                return 0
            for unit, multiplier in [("亿", 100000000), ("万", 10000), ("w", 10000), ("k", 1000)]:
                if unit in s.lower():
                    try:
                        return int(float(s.lower().replace(unit, "")) * multiplier)
                    except ValueError:
                        pass
            try:
                return int(float(s))
            except (ValueError, TypeError):
                return 0

        def _score(it):
            return _parse_count(it.get("plays", 0)) + _parse_count(it.get("likes", 0)) * 2

        sorted_items = sorted(items, key=_score, reverse=True)[:10]
        trend_items = [
            TrendItem(
                title=it.get("title", ""),
                platform=platform,
                viral_score=50,
                trend_reason="(降级模式: 纯热度排序)",
                category="",
                engagement={"plays": it.get("plays", "0"), "likes": it.get("likes", "0")},
                raw=it,
            )
            for it in sorted_items
        ]
        return TrendReport(
            platform=platform,
            keyword=keyword or "hot",
            total_candidates=len(trend_items),
            items=trend_items,
            summary="LLM 不可用，降级为热度排序",
        )
