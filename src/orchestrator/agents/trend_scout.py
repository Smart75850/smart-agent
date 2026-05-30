"""Trend Scout Agent — 爆款趨勢分析。

Flow:
  1. 採集目標平台 hot/search 數據
  2. DeepSeek V4 Flash 分析爆款規律
  3. 輸出爆款候選列表 (viral_score + trend_reason)

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
    # 简体/异体 → 标准繁体
    "美妆": "美妝", "财经": "財經", "游戏": "遊戲", "娱乐": "娛樂",
    "旅游": "旅遊", "母婴": "母嬰", "宠物": "寵物", "健康": "健康/醫療",
    "医疗": "健康/醫療", "健身运动": "健身",
    # 科技/数码相关
    "數碼": "科技/AI", "数码": "科技/AI", "科技": "科技/AI",
    "AI": "科技/AI", "人工智能": "科技/AI", "AI工具": "科技/AI",
    # 教育相关
    "学习": "教育", "考试": "教育",
    # 家居相关
    "房产": "家居", "装修": "家居", "房地产": "家居",
    # 财经相关
    "金融": "財經", "投资": "財經", "理财": "財經",
    # 其他常见输出
    "搞笑": "娛樂", "综艺": "娛樂", "明星": "娛樂",
    "汽车": "其他", "职场": "其他",
}

_CATEGORY_VALUES = frozenset([
    "科技/AI", "美妝", "美食", "穿搭", "家居", "健身", "教育",
    "財經", "遊戲", "娛樂", "旅遊", "母嬰", "寵物", "健康/醫療", "其他",
])


# ── Pydantic 结构化输出模型 ─────────────────────────────────

class TrendScoutItemOutput(BaseModel):
    index: int = Field(description="内容在输入列表中的索引")
    viral_score: int = Field(ge=0, le=100, description="爆款潜力分：90+蓝海/70-89有需求/50-69红海/<50小众")
    trend_reason: str = Field(min_length=40, description="爆款原因分析，引用具体数据+爆款机制")
    category: Literal["科技/AI", "美妝", "美食", "穿搭", "家居", "健身", "教育", "財經", "遊戲", "娛樂", "旅遊", "母嬰", "寵物", "健康/醫療", "其他"] = Field(description="分类枚举")

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
            logger.warning(f"TrendScout: [{platform}] 無數據，跳過分析")
            return TrendReport(platform=platform, keyword=keyword, total_candidates=0)

        report = await self._llm_generate(platform, keyword, items)
        logger.info(
            f"TrendScout: [{platform}] {report.total_candidates} 個爆款候選"
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
        {"title": "我用AI做了一個能自動回覆客服的機器人，成本只花了50塊", "plays": "85万", "likes": "4.2万",
         "viral_score": 92, "category": "科技/AI",
         "trend_reason": "AI工具實操+極低成本+個人即商用，三層鉤子疊加；互動比4.9%遠超均值，藍海信號明確"},
        {"title": "小個子女生這樣穿顯高10cm！5套通勤穿搭公式", "plays": "120万", "likes": "6.8万",
         "viral_score": 85, "category": "穿搭",
         "trend_reason": "精準人群（小個子）+ 數字衝擊（10cm）+ 公式化教程（可收藏），互動比5.7%"},
        {"title": "小學五年級數學這樣教，孩子終於聽懂了｜分數加減法", "plays": "45万", "likes": "2.1万",
         "viral_score": 78, "category": "教育",
         "trend_reason": "垂直剛需（家長痛點）+ 教學實用性強 + 標題含關鍵詞利於搜索，教育賽道持續有需求"},
        {"title": "黑神話悟空隱藏BOSS位置全攻略，第7個99%人不知道", "plays": "320万", "likes": "15万",
         "viral_score": 88, "category": "遊戲",
         "trend_reason": "蹭熱門遊戲IP+數字列舉+稀缺性（99%人不知道），攻略類內容天然有收藏價值"},
        {"title": "3種食材5分鐘搞定週末早餐，比外面賣的好吃10倍", "plays": "68万", "likes": "3.5万",
         "viral_score": 76, "category": "美食",
         "trend_reason": "數字簡化（3食材5分鐘）+ 對比錨定（比外面好吃）+ 場景精準（週末），實用型爆款"},
    ]

    _FEWSHOT_BAD = [
        {"title": "今天的天氣真好呀陽光明媚", "plays": "1.2万", "likes": "200",
         "viral_score": 8, "category": "其他",
         "trend_reason": "❌ 錯誤示範：純個人生活記錄、無任何爆款元素、互動比僅1.7%，不應高估此類內容"},
        {"title": "推薦一個很好用的東西給大家", "plays": "5000", "likes": "150",
         "viral_score": 12, "category": "其他",
         "trend_reason": "❌ 錯誤示範：標題模糊無具體信息、無品類關鍵詞、無數字無情緒、無搜索價值"},
    ]

    async def _llm_generate(
        self, platform: str, keyword: str, items: list[dict]
    ) -> TrendReport:
        """DeepSeek LLM 分析爆款趨勢（v2 增強 prompt）。"""
        if not self._api_key:
            logger.info("DeepSeek API key 未設定，使用純熱度排序")
            return self._fallback(platform, keyword, items)

        items_text = "\n".join(
            f"{i}. {it.get('title','')} | 播放:{it.get('plays','0')} | 讚:{it.get('likes','0')} | 作者:{it.get('author','')}"
            for i, it in enumerate(items[:15])
        )

        good_examples_text = "\n".join(
            f"  ✅ [{ex['category']}] score={ex['viral_score']} | {ex['title'][:50]}\n     → {ex['trend_reason']}"
            for ex in self._FEWSHOT_GOOD
        )
        bad_examples_text = "\n".join(
            f"  ❌ [{ex['category']}] score={ex['viral_score']} | {ex['title'][:50]}\n     → {ex['trend_reason']}"
            for ex in self._FEWSHOT_BAD
        )

        context = f"平台: {platform}" + (f", 關鍵詞: {keyword}" if keyword else " (熱榜)")
        prompt = f"""你是頂級內容趨勢分析師（Trend Scout），專門從社交媒體數據中識別具有爆款潛力的內容。

## 任務
分析以下 {context} 的內容列表，為每條內容評分並解釋爆款潛力。

## 品質標準
- 好的分析：有具體數據支撐、引用互動指標、指出可複製的爆款機制、分類精確
- 差的分析：空泛描述如「內容不錯」「有潛力」、分類選「其他」偷懶、無視數據只憑標題猜

## 爆款判定規則
一條內容被視為有爆款潛力，必須滿足以下 4 項中至少 2 項：
1. **互動比異常** — 讚/播 > 3% 或 評論/播 > 0.5%（高於平台均值）
2. **熱門賽道** — 屬於當前增長中的內容賽道
3. **情緒觸發** — 標題含強烈情緒信號（好奇/共鳴/焦慮/憤怒/驚喜）
4. **形式創新** — 內容形式有別於同賽道常規做法

## 分類枚舉（必須從以下選一，不得自創）
科技/AI、美妝、美食、穿搭、家居、健身、教育、財經、遊戲、娛樂、旅遊、母嬰、寵物、健康/醫療、其他
⚠️ 「其他」僅限以下情況才能用：內容無主題（如日常隨拍、純閒聊）。如果內容涉及任何產品/話題/領域，必須選擇最接近的分類。嚴禁因懶得判斷而選「其他」。每批最多 1 個「其他」，超過則按錯誤處理。如果不確定選哪個分類，選最接近的兩個分類中更具體的那個。

## viral_score 評分錨點
- 90-100：藍海信號 — 互動比 >5% + 新賽道/新形式 + 可大量複製
- 70-89：有明確需求 — 互動比 >3% + 熱門賽道 + 有可複製元素
- 50-69：紅海競爭 — 互動正常但賽道擁擠，需差異化才能突圍
- <50：小眾或低互動 — 互動比低或受眾太窄

## Few-Shot 正例（學習這些分析的深度和具體度）
{good_examples_text}

## Few-Shot 負例（避免以下空洞/錯誤的分析）
{bad_examples_text}

## 邊界情況處理
- 數據缺失（播放/讚為 0）：標註 confidence=low，viral_score 不超過 50
- 標題含明顯廣告/營銷話術：標註為商業內容，viral_score 扣 20 分
- 跨類別內容（如科技+教育）：選主類別，trend_reason 提及次要類別

## 待分析內容
{items_text}"""

        try:
            output = await self._call_llm_with_critic(prompt, TrendScoutOutput, "trend_scout", temperature=0.3)

            trend_items = []
            for ti in output.items:
                idx = ti.index
                src = items[idx] if 0 <= idx < len(items) else {}
                trend_items.append(TrendItem(
                    title=src.get("title", ""),
                    platform=platform,
                    viral_score=ti.viral_score,
                    trend_reason=ti.trend_reason,
                    category=ti.category,
                    engagement={"plays": src.get("plays", "0"), "likes": src.get("likes", "0")},
                    raw=src,
                ))

            trend_items.sort(key=lambda x: x.viral_score, reverse=True)
            return TrendReport(
                platform=platform,
                keyword=keyword or "hot",
                total_candidates=len(trend_items),
                items=trend_items,
                summary=output.summary,
            )

        except Exception as exc:
            logger.warning(f"TrendScout LLM 失敗，降級為熱度排序: {exc}")
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
                trend_reason="(降級模式: 純熱度排序)",
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
            summary="LLM 不可用，降級為熱度排序",
        )
