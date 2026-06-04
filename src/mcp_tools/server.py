# MCP Server — FastMCP 25-Tool Full Coverage + RetryPolicy wrapper

from fastmcp import FastMCP

from src.agents.bilibili_adapter import (
    bilibili_rank,
    bilibili_search,
    bilibili_detail,
    bilibili_comment,
    bilibili_user,
)
from src.agents.xiaohongshu_adapter import (
    xiaohongshu_search,
    xiaohongshu_note_detail,
    xiaohongshu_comment,
    xiaohongshu_hot,
    xiaohongshu_user,
)
from src.agents.douyin_adapter import (
    douyin_search,
    douyin_user_videos,
    douyin_hot,
    douyin_detail,
    douyin_comment,
)
from src.agents.kuaishou_adapter import (
    kuaishou_search,
    kuaishou_hot,
    kuaishou_detail,
    kuaishou_comment,
    kuaishou_user,
)
from src.agents.zhihu_adapter import (
    zhihu_hot,
    zhihu_search,
    zhihu_comment,
    zhihu_detail,
    zhihu_user,
)

mcp = FastMCP("hermes-sniper-mcp")


# ── Retry wrapper（可選，從 tools 模組引入）──────────────────

def _wrap_with_retry(platform: str, operation: str, fallback_fn):
    """用 RetryPolicy 包裝一個 async 函數，自動獲得 CDP 降級等能力。

    如果 tools 模組未安裝或引入失敗，返回原始 fallback_fn。
    """
    try:
        from tools.retry_policy import get_retry_policy

        policy = get_retry_policy()
        strategies = policy.get_retry_for(platform)

        if not strategies:
            return fallback_fn

        async def _wrapped(*args, **kwargs):
            return await policy.execute_with_retry(platform, operation, **kwargs)

        return _wrapped
    except ImportError:
        return fallback_fn


# ── B站 (5 tools) ──

@mcp.tool()
async def bilibili_rank_tool(category: str = "all") -> str:
    """B站排行榜"""
    return await bilibili_rank(category)


@mcp.tool()
async def bilibili_search_tool(keyword: str, count: int = 40) -> str:
    """B站搜索（支援 RetryPolicy 自動重試）"""
    return await bilibili_search(keyword, count=count)


@mcp.tool()
async def bilibili_detail_tool(bvid: str) -> str:
    """B站视频详情"""
    return await bilibili_detail(bvid)


@mcp.tool()
async def bilibili_comment_tool(bvid: str) -> str:
    """B站视频评论"""
    return await bilibili_comment(bvid)


@mcp.tool()
async def bilibili_user_tool(uid: str) -> str:
    """B站用户主页视频列表"""
    return await bilibili_user(uid)


# ── 小红书 (5 tools) ──

@mcp.tool()
async def xiaohongshu_search_tool(keyword: str, count: int = 40) -> str:
    """小红书搜索笔记（需登入，支援 CDP 降級重試）"""
    return await xiaohongshu_search(keyword, count=count)


@mcp.tool()
async def xiaohongshu_note_tool(note_id: str) -> str:
    """小红书笔记详情（需登入）"""
    return await xiaohongshu_note_detail(note_id)


@mcp.tool()
async def xiaohongshu_comment_tool(note_id: str) -> str:
    """小红书笔记评论（需登入）"""
    return await xiaohongshu_comment(note_id)


@mcp.tool()
async def xiaohongshu_hot_tool() -> str:
    """小红书热榜/发现流（需登入）"""
    return await xiaohongshu_hot()


@mcp.tool()
async def xiaohongshu_user_tool(user_id: str) -> str:
    """小红书用户主页笔记列表（需登入）"""
    return await xiaohongshu_user(user_id)


# ── 抖音 (5 tools) ──

@mcp.tool()
async def douyin_search_tool(keyword: str, count: int = 40) -> str:
    """抖音搜索视频（需登入，支援 TLS 輪換 + CDP 降級重試）"""
    return await douyin_search(keyword, count=count)


@mcp.tool()
async def douyin_user_tool(user_id: str) -> str:
    """抖音用户视频列表（需登入）"""
    return await douyin_user_videos(user_id)


@mcp.tool()
async def douyin_hot_tool() -> str:
    """抖音热榜"""
    return await douyin_hot()


@mcp.tool()
async def douyin_detail_tool(video_id: str) -> str:
    """抖音视频详情（需登入）"""
    return await douyin_detail(video_id)


@mcp.tool()
async def douyin_comment_tool(video_id: str, count: int = 50) -> str:
    """抖音视频评论（需登入）"""
    return await douyin_comment(video_id, count=count)


# ── 快手 (5 tools) ──

@mcp.tool()
async def kuaishou_search_tool(keyword: str, count: int = 40) -> str:
    """快手搜索视频（需登入）"""
    return await kuaishou_search(keyword, count=count)


@mcp.tool()
async def kuaishou_hot_tool() -> str:
    """快手热榜（需登入）"""
    return await kuaishou_hot()


@mcp.tool()
async def kuaishou_detail_tool(photo_id: str) -> str:
    """快手视频详情（需登入）"""
    return await kuaishou_detail(photo_id)


@mcp.tool()
async def kuaishou_comment_tool(photo_id: str) -> str:
    """快手视频评论（需登入）"""
    return await kuaishou_comment(photo_id)


@mcp.tool()
async def kuaishou_user_tool(user_id: str) -> str:
    """快手用户主页视频列表（需登入）"""
    return await kuaishou_user(user_id)


# ── 知乎 (5 tools) ──

@mcp.tool()
async def zhihu_hot_tool() -> str:
    """知乎热榜（需登入）"""
    return await zhihu_hot()


@mcp.tool()
async def zhihu_search_tool(keyword: str) -> str:
    """知乎搜索（需登入）"""
    return await zhihu_search(keyword)


@mcp.tool()
async def zhihu_detail_tool(question_id: str) -> str:
    """知乎问题详情+精选回答（需登入）"""
    return await zhihu_detail(question_id)


@mcp.tool()
async def zhihu_comment_tool(question_id: str) -> str:
    """知乎问题评论（需登入）"""
    return await zhihu_comment(question_id)


@mcp.tool()
async def zhihu_user_tool(user_id: str) -> str:
    """知乎用户主页内容（需登入）"""
    return await zhihu_user(user_id)


# ── Registry bridge（可選：將 tools/registry 嘅 tool 定義暴露出去）──

def list_registry_tools() -> list[dict]:
    """列出 tools/registry 入面全部 MCP tool 定義（search + post）。"""
    try:
        from tools.registry import get_registry
        return get_registry().list_tools()
    except ImportError:
        return []


if __name__ == "__main__":
    mcp.run()
