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

from src.orchestrator.agents.base import BaseAgent
from src.utils.logger import logger


@dataclass
class SentimentItem:
    title: str
    platform: str
    sentiment: str = ""           # positive / neutral / negative / mixed
    positive_pct: int = 0
    neutral_pct: int = 0
    negative_pct: int = 0
    key_insights: str = ""        # 關鍵洞察
    audience_reaction: str = ""   # 受眾反應摘要


@dataclass
class SentimentReport:
    platform: str
    total_analyzed: int
    items: list[SentimentItem] = field(default_factory=list)
    overall_sentiment: str = ""
    summary: str = ""


class SentimentReader(BaseAgent):
    """評論情緒分析 Agent。"""

    async def run(self, items: list, platform: str = "", fetch_comments: bool = True) -> SentimentReport:
        """主入口。

        Args:
            items: 內容列表 (dict with title/platform_id)
            platform: 平台名
            fetch_comments: 是否拉取真實評論 (需 CDP browser)
        """
        if not items:
            return SentimentReport(platform=platform, total_analyzed=0)

        # 嘗試拉取評論
        comments_data = {}
        if fetch_comments:
            comments_data = await self._fetch_comments(items, platform)

        if not self._api_key:
            return self._fallback(items, platform, comments_data)

        return await self._llm_generate(items, platform, comments_data)

    async def as_node(self, state: dict) -> dict:
        trend_reports = state.get("trend_reports", {})
        all_sentiments = []
        summaries = []

        for p, report_dict in trend_reports.items():
            items = report_dict.get("items", [])
            if items:
                raw_items = [it.get("raw", {}) for it in items if isinstance(it, dict)]
                report = await self.run(items=raw_items[:3], platform=p, fetch_comments=False)
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
            for item in items[:3]:
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

    async def _llm_generate(
        self, items: list, platform: str, comments_data: dict
    ) -> SentimentReport:
        items_text = "\n".join(
            f"{i}. {it.get('title','')} | 播放:{it.get('plays','0')} | 讚:{it.get('likes','0')}"
            + (f" | 評論:{comments_data.get(it.get('platform_id','') or it.get('bvid',''), [])[:5]}"
               if comments_data.get(it.get('platform_id','') or it.get('bvid','')) else "")
            for i, it in enumerate(items[:10])
        )

        prompt = (
            f"分析以下{platform}內容的受眾情緒反應：\n\n"
            f"{items_text}\n\n"
            f"請返回 JSON（不要 markdown 代碼塊）：\n"
            f'{{"overall_sentiment": "整體情緒傾向", "summary": "一句話總結", '
            f'"items": [{{"index": 數字, "sentiment": "positive/neutral/negative/mixed", '
            f'"positive_pct": 0-100, "neutral_pct": 0-100, "negative_pct": 0-100, '
            f'"key_insights": "關鍵洞察", "audience_reaction": "受眾反應一句話"}}]}}'
        )

        try:
            content = await self._call_llm(prompt, temperature=0.3, json_mode=True)
            parsed = self._parse_json(content)

            sentiment_items = []
            for s in parsed.get("items", []):
                idx = s.get("index", 0)
                src = items[idx] if 0 <= idx < len(items) else {}
                sentiment_items.append(SentimentItem(
                    title=src.get("title", ""),
                    platform=platform,
                    sentiment=s.get("sentiment", "neutral"),
                    positive_pct=int(s.get("positive_pct", 0)),
                    neutral_pct=int(s.get("neutral_pct", 0)),
                    negative_pct=int(s.get("negative_pct", 0)),
                    key_insights=s.get("key_insights", ""),
                    audience_reaction=s.get("audience_reaction", ""),
                ))

            return SentimentReport(
                platform=platform,
                total_analyzed=len(sentiment_items),
                items=sentiment_items,
                overall_sentiment=parsed.get("overall_sentiment", ""),
                summary=parsed.get("summary", ""),
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
