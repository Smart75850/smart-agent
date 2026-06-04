"""RetryPolicy — per-platform self-healing retry chains with async execution.

XHS and Douyin have CDP browser fallback; other 5 use HTTP direct retry.
All handlers use lazy resolution (inline imports) to avoid circular imports.
"""

from __future__ import annotations

import asyncio
import logging

from tools.mcp_types import MCPToolResult, RetryStrategy

logger = logging.getLogger(__name__)

_PLATFORM_STRATEGIES: dict[str, list[RetryStrategy]] = {}

# ── Lazy async handler factories ──────────────────────────────


async def _search_xhs(keyword: str, count: int = 20) -> MCPToolResult:
    from src.agents.xiaohongshu_adapter import XiaohongshuAdapter
    adapter = XiaohongshuAdapter()
    items = await adapter.search(keyword, limit=count)
    return MCPToolResult(content=[{"type": "json", "data": items}])


async def _search_douyin(keyword: str, count: int = 20) -> MCPToolResult:
    import json
    from src.agents.douyin_adapter import douyin_search
    result_json = await douyin_search(keyword, count=count)
    items = json.loads(result_json) if result_json else []
    return MCPToolResult(content=[{"type": "json", "data": items}])


async def _search_bilibili(keyword: str, count: int = 20) -> MCPToolResult:
    from src.utils.bilibili_http import search_all
    items = await search_all(keyword, limit=count)
    return MCPToolResult(content=[{"type": "json", "data": items}])


async def _search_zhihu(keyword: str, count: int = 20) -> MCPToolResult:
    from src.utils.zh_http import search_all
    items = await search_all(keyword, limit=count)
    return MCPToolResult(content=[{"type": "json", "data": items}])


async def _search_kuaishou(keyword: str, count: int = 20) -> MCPToolResult:
    from src.utils.ks_http import search_all
    items = await search_all(keyword, limit=count)
    return MCPToolResult(content=[{"type": "json", "data": items}])


async def _search_weibo(keyword: str, count: int = 20) -> MCPToolResult:
    from src.utils.weibo_http import search_all
    items = await search_all(keyword, limit=count)
    return MCPToolResult(content=[{"type": "json", "data": items}])


async def _search_tieba(keyword: str, count: int = 20) -> MCPToolResult:
    from src.utils.tieba_http import search_all
    items = await search_all(keyword, limit=count)
    return MCPToolResult(content=[{"type": "json", "data": items}])


_HANDLER_MAP: dict[str, dict[str, callable]] = {
    "xiaohongshu": {"search": _search_xhs},
    "douyin": {"search": _search_douyin},
    "bilibili": {"search": _search_bilibili},
    "zhihu": {"search": _search_zhihu},
    "kuaishou": {"search": _search_kuaishou},
    "weibo": {"search": _search_weibo},
    "tieba": {"search": _search_tieba},
}


def _build_strategies():
    """Build per-platform retry chains."""

    # XHS chain: http(2次) → CDP fallback → 60s delay retry
    _PLATFORM_STRATEGIES["xiaohongshu"] = [
        RetryStrategy(name="xhs_http", max_attempts=2, delay_seconds=2.0, use_cdp=False),
        RetryStrategy(name="xhs_cdp_fallback", max_attempts=1, delay_seconds=5.0, use_cdp=True),
        RetryStrategy(name="xhs_delay_retry", max_attempts=1, delay_seconds=60.0, use_cdp=True),
    ]

    # Douyin chain: http(2次) → TLS rotate → CDP fallback
    _PLATFORM_STRATEGIES["douyin"] = [
        RetryStrategy(name="douyin_http", max_attempts=2, delay_seconds=2.0, use_cdp=False),
        RetryStrategy(name="douyin_tls_rotate", max_attempts=1, delay_seconds=3.0, use_tls_rotate=True),
        RetryStrategy(name="douyin_cdp_fallback", max_attempts=1, delay_seconds=5.0, use_cdp=True),
    ]

    # Other 5: http direct (3次)
    for p in ["bilibili", "zhihu", "kuaishou", "weibo", "tieba"]:
        _PLATFORM_STRATEGIES[p] = [
            RetryStrategy(name=f"{p}_http", max_attempts=3, delay_seconds=1.0, use_cdp=False),
        ]


class RetryPolicy:
    """Per-platform retry policy with self-healing chains + async execution engine.

    XHS/Douyin have CDP browser fallback for maximum resilience.
    Other 5 platforms use HTTP direct with up to 3 attempts.
    """

    def __init__(self):
        if not _PLATFORM_STRATEGIES:
            _build_strategies()

    def get_retry_for(self, platform: str) -> list[RetryStrategy]:
        """Return the ordered list of retry strategies for a platform."""
        return _PLATFORM_STRATEGIES.get(platform, [])

    @property
    def platforms(self) -> list[str]:
        return list(_PLATFORM_STRATEGIES.keys())

    async def execute_with_retry(
        self, platform: str, operation: str = "search", **kwargs
    ) -> MCPToolResult:
        """Execute an operation with full retry chain.

        Walks through strategies in order. For each strategy, tries up to
        max_attempts times. On first success, returns immediately.
        On all strategies exhausted, returns the last error result.

        Args:
            platform: 平台名稱 (bilibili/douyin/...)
            operation: 操作類型 (search / post)
            **kwargs: 傳俾 handler 嘅參數 (keyword, count, ...)
        """
        strategies = self.get_retry_for(platform)
        if not strategies:
            return MCPToolResult(
                content=[{"type": "error", "message": f"無重試策略: {platform}"}],
                is_error=True,
                metadata={"platform": platform, "operation": operation},
            )

        handler = _HANDLER_MAP.get(platform, {}).get(operation)
        if handler is None:
            return MCPToolResult(
                content=[{"type": "error", "message": f"無處理器: {platform}/{operation}"}],
                is_error=True,
                metadata={"platform": platform, "operation": operation},
            )

        keyword = kwargs.get("keyword", "")
        count = kwargs.get("count", 20)

        last_result: MCPToolResult | None = None
        total_attempts = 0

        for strategy in strategies:
            for attempt in range(1, strategy.max_attempts + 1):
                total_attempts += 1
                try:
                    result = await handler(keyword, count)
                    if not result.is_error and result.content:
                        result.metadata["retry_count"] = total_attempts
                        result.metadata["strategy_used"] = strategy.name
                        return result
                    last_result = result
                except Exception as exc:
                    logger.warning(
                        f"[{platform}] {strategy.name} 第{attempt}次失敗: {exc}"
                    )
                    last_result = MCPToolResult(
                        content=[{"type": "error", "message": str(exc)}],
                        is_error=True,
                        metadata={"platform": platform, "strategy": strategy.name, "attempt": attempt},
                    )

                if attempt < strategy.max_attempts and strategy.delay_seconds > 0:
                    await asyncio.sleep(strategy.delay_seconds)

            # 當前策略全部失敗，等 strategy 之間嘅延遲
            if strategy.delay_seconds > 0:
                await asyncio.sleep(strategy.delay_seconds)

        # 全部策略失敗
        if last_result is None:
            last_result = MCPToolResult(
                content=[{"type": "error", "message": "全部重試策略耗盡"}],
                is_error=True,
            )
        last_result.metadata["retry_count"] = total_attempts
        last_result.metadata["total_strategies"] = len(strategies)
        return last_result


_policy: RetryPolicy | None = None


def get_retry_policy() -> RetryPolicy:
    global _policy
    if _policy is None:
        _policy = RetryPolicy()
    return _policy
