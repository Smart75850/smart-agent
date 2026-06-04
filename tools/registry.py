"""ToolRegistry — 7-platform MCP tool registry with lazy handler imports.

Wraps existing src/utils/* and src/agents/* modules without modifying them.
Provides both search (讀) and post (寫) tool definitions per platform.
"""

from __future__ import annotations

import logging

from tools.mcp_types import MCPTool, MCPToolResult

logger = logging.getLogger(__name__)

_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "keyword": {"type": "string", "description": "搜索关键词"},
        "count": {"type": "integer", "description": "返回结果数量", "default": 20},
    },
    "required": ["keyword"],
}

_POST_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "標題"},
        "content": {"type": "string", "description": "正文內容"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "標籤列表"},
    },
    "required": ["title", "content"],
}


def _build_tools() -> list[MCPTool]:
    """Build all MCP tool definitions — search + post for each platform."""
    return [
        # ── Search tools ──────────────────────────────────
        MCPTool(
            name="bilibili_search",
            description="B站视频搜索 — Wbi 签名 + curl_cffi TLS 指纹，零浏览器",
            input_schema=_SEARCH_SCHEMA,
            handler=_search_bilibili,
        ),
        MCPTool(
            name="xiaohongshu_search",
            description="小红书笔记搜索 — CDP/HTTP 双路径",
            input_schema=_SEARCH_SCHEMA,
            handler=_search_xiaohongshu,
        ),
        MCPTool(
            name="douyin_search",
            description="抖音视频搜索 — Session HTTP → SignSrv → CDP 三路径",
            input_schema=_SEARCH_SCHEMA,
            handler=_search_douyin,
        ),
        MCPTool(
            name="zhihu_search",
            description="知乎内容搜索 — curl_cffi TLS 指纹 + 持久化会话",
            input_schema=_SEARCH_SCHEMA,
            handler=_search_zhihu,
        ),
        MCPTool(
            name="kuaishou_search",
            description="快手视频搜索 — httpx + cookies，零浏览器",
            input_schema=_SEARCH_SCHEMA,
            handler=_search_kuaishou,
        ),
        MCPTool(
            name="weibo_search",
            description="微博内容搜索 — httpx + cookies，零浏览器",
            input_schema=_SEARCH_SCHEMA,
            handler=_search_weibo,
        ),
        MCPTool(
            name="tieba_search",
            description="贴吧帖子搜索 — curl_cffi + MD5 签名，零浏览器",
            input_schema=_SEARCH_SCHEMA,
            handler=_search_tieba,
        ),
        # ── Post tools ────────────────────────────────────
        MCPTool(
            name="bilibili_post",
            description="B站发布动态 — HTTP API（待實現）",
            input_schema=_POST_SCHEMA,
            handler=_post_stub("bilibili", "发布动态"),
        ),
        MCPTool(
            name="xiaohongshu_post",
            description="小红书发布笔记 — CDP 瀏覽器（待實現）",
            input_schema=_POST_SCHEMA,
            handler=_post_stub("xiaohongshu", "发布笔记"),
        ),
        MCPTool(
            name="douyin_post",
            description="抖音发布视频 — HTTP/CDP（待實現）",
            input_schema=_POST_SCHEMA,
            handler=_post_stub("douyin", "发布视频"),
        ),
        MCPTool(
            name="zhihu_post",
            description="知乎发布文章 — HTTP API（待實現）",
            input_schema=_POST_SCHEMA,
            handler=_post_stub("zhihu", "发布文章"),
        ),
        MCPTool(
            name="kuaishou_post",
            description="快手发布视频 — HTTP API（待實現）",
            input_schema=_POST_SCHEMA,
            handler=_post_stub("kuaishou", "发布视频"),
        ),
        MCPTool(
            name="weibo_post",
            description="微博发帖 — HTTP API（待實現）",
            input_schema=_POST_SCHEMA,
            handler=_post_stub("weibo", "发帖"),
        ),
        MCPTool(
            name="tieba_post",
            description="贴吧发帖 — HTTP API（待實現）",
            input_schema=_POST_SCHEMA,
            handler=_post_stub("tieba", "发帖"),
        ),
    ]


# ── Lazy search handlers ──────────────────────────────────────


async def _search_bilibili(keyword: str, count: int = 20) -> MCPToolResult:
    from src.utils.bilibili_http import search_all
    items = await search_all(keyword, limit=count)
    return MCPToolResult(content=[{"type": "json", "data": items}])


async def _search_xiaohongshu(keyword: str, count: int = 20) -> MCPToolResult:
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


# ── Post stubs (待平台層實現後替換) ──────────────────────────


def _post_stub(platform: str, label: str):
    """返回一個 async handler，標記該平台的發布功能尚未實現。"""
    async def _stub(title: str, content: str, tags: list[str] | None = None, **kwargs) -> MCPToolResult:
        logger.warning(f"[{platform}] {label}尚未實現 — title={title[:40]}")
        return MCPToolResult(
            content=[{
                "type": "error",
                "message": f"{platform} {label}功能尚未實現，請先用 CDP 瀏覽器手動操作",
                "platform": platform,
                "title": title,
            }],
            is_error=True,
            metadata={"platform": platform, "operation": "post", "status": "not_implemented"},
        )
    return _stub


# ── Registry ───────────────────────────────────────────────────


class ToolRegistry:
    """MCP-compliant tool registry managing search + post tools for 7 platforms."""

    def __init__(self):
        self._tools: dict[str, MCPTool] = {}
        self._register_all()

    def _register_all(self):
        for tool in _build_tools():
            self._tools[tool.name] = tool

    def list_tools(self) -> list[dict]:
        return [t.to_mcp_json() for t in self._tools.values()]

    def list_search_tools(self) -> list[dict]:
        return [t.to_mcp_json() for t in self._tools.values()
                if t.name.endswith("_search")]

    def list_post_tools(self) -> list[dict]:
        return [t.to_mcp_json() for t in self._tools.values()
                if t.name.endswith("_post")]

    def get_tool(self, name: str) -> MCPTool | None:
        return self._tools.get(name)

    async def execute(self, name: str, **kwargs) -> MCPToolResult:
        """直接執行一個 tool（唔經過重試）。"""
        tool = self._tools.get(name)
        if tool is None:
            return MCPToolResult(
                content=[{"type": "error", "message": f"未知工具: {name}"}],
                is_error=True,
                metadata={"tool_name": name, "available": list(self._tools.keys())},
            )

        if tool.handler is None:
            return MCPToolResult(
                content=[{"type": "error", "message": f"工具無處理器: {name}"}],
                is_error=True,
            )

        return await tool.handler(**kwargs)

    async def execute_with_retry(self, name: str, **kwargs) -> MCPToolResult:
        """執行 tool，自動綁定對應平台嘅重試策略。"""
        from tools.retry_policy import get_retry_policy

        tool = self._tools.get(name)
        if tool is None:
            return MCPToolResult(
                content=[{"type": "error", "message": f"未知工具: {name}"}],
                is_error=True,
            )

        # 從 tool name 推斷平台名: "bilibili_search" → "bilibili"
        platform = name.rsplit("_", 1)[0]
        operation = name.rsplit("_", 1)[1]  # "search" or "post"

        policy = get_retry_policy()
        return await policy.execute_with_retry(platform, operation, **kwargs)


_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
