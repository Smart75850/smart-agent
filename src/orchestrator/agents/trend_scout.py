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

import httpx

from config.settings import settings
from src.utils.logger import logger


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


class TrendScout:
    """爆款趨勢分析 Agent。"""

    def __init__(self):
        self._api_key = settings.DEEPSEEK_API_KEY or settings.LLM_API_KEY
        self._api_url = settings.DEEPSEEK_API_URL or settings.LLM_API_URL or "https://api.deepseek.com/v1"
        self._model = settings.DEEPSEEK_MODEL or settings.LLM_MODEL or "deepseek-chat"

    # ── public API ────────────────────────────────────────────

    async def run(
        self,
        platform: str = "bilibili",
        keyword: str = "",
        limit: int = 20,
    ) -> TrendReport:
        """主入口：採集 + 分析，返回 TrendReport。"""
        items = await self._collect(platform, keyword, limit)
        if not items:
            logger.warning(f"TrendScout: [{platform}] 無數據，跳過分析")
            return TrendReport(platform=platform, keyword=keyword, total_candidates=0)

        report = await self._analyze(platform, keyword, items)
        logger.info(
            f"TrendScout: [{platform}] {report.total_candidates} 個爆款候選"
        )
        return report

    async def as_node(self, state: dict) -> dict:
        """LangGraph 節點接口。"""
        keyword = state.get("keyword", "")
        platforms = state.get("platforms", ["bilibili"])
        merged = state.get("merged_items", [])

        all_reports = {}
        for p in platforms:
            items = [it for it in merged if it.get("platform") == p]
            if not items:
                items = await self._collect(p, keyword, limit=state.get("limit", 20))
            if items:
                report = await self._analyze(p, keyword, items)
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

    async def _analyze(
        self, platform: str, keyword: str, items: list[dict]
    ) -> TrendReport:
        """DeepSeek LLM 分析爆款趨勢。"""
        if not self._api_key:
            logger.info("DeepSeek API key 未設定，使用純熱度排序")
            return self._fallback_sort(platform, keyword, items)

        items_text = "\n".join(
            f"{i}. {it.get('title','')} | 播放:{it.get('plays','0')} | 讚:{it.get('likes','0')} | 作者:{it.get('author','')}"
            for i, it in enumerate(items[:15])
        )

        context = f"平台: {platform}" + (f", 關鍵詞: {keyword}" if keyword else " (熱榜)")
        prompt = (
            f"分析以下{context}的內容列表，找出爆款趨勢：\n\n"
            f"{items_text}\n\n"
            f"請返回 JSON，格式如下（不要 markdown 代碼塊）：\n"
            f'{{"summary": "一句話總結整體趨勢", '
            f'"items": [{{"index": 數字, "viral_score": 0-100, '
            f'"trend_reason": "一句話爆款原因", "category": "品類"}}]}}'
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
                        "temperature": 0.3,
                        "max_tokens": 2000,
                    },
                )
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)

                trend_items = []
                for ti in parsed.get("items", []):
                    idx = ti.get("index", 0)
                    src = items[idx] if 0 <= idx < len(items) else {}
                    trend_items.append(TrendItem(
                        title=src.get("title", ""),
                        platform=platform,
                        viral_score=int(ti.get("viral_score", 50)),
                        trend_reason=ti.get("trend_reason", ""),
                        category=ti.get("category", ""),
                        engagement={"plays": src.get("plays", "0"), "likes": src.get("likes", "0")},
                        raw=src,
                    ))

                trend_items.sort(key=lambda x: x.viral_score, reverse=True)
                return TrendReport(
                    platform=platform,
                    keyword=keyword or "hot",
                    total_candidates=len(trend_items),
                    items=trend_items,
                    summary=parsed.get("summary", ""),
                )

        except Exception as exc:
            logger.warning(f"TrendScout LLM 失敗，降級為熱度排序: {exc}")
            return self._fallback_sort(platform, keyword, items)

    def _fallback_sort(self, platform: str, keyword: str, items: list[dict]) -> TrendReport:
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
