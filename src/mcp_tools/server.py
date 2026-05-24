# MCP Server — FastMCP 雙模式
# 開源版 v0.1.0：純爬蟲，輸出 raw JSON

from fastmcp import FastMCP

from src.agents.bilibili_adapter import bilibili_rank, bilibili_search
from src.agents.xiaohongshu_adapter import xiaohongshu_search, xiaohongshu_note_detail
from src.agents.douyin_adapter import douyin_search, douyin_user_videos
from src.agents.kuaishou_adapter import kuaishou_search, kuaishou_hot
from src.agents.zhihu_adapter import zhihu_hot, zhihu_search

mcp = FastMCP("hermes-sniper-mcp")


# ── B站 ──

@mcp.tool()
async def bilibili_rank_tool(category: str = "all") -> str:
    """B站排行榜爬取"""
    return await bilibili_rank(category)


@mcp.tool()
async def bilibili_search_tool(keyword: str) -> str:
    """B站搜索"""
    return await bilibili_search(keyword)


# ── 小紅書 ──

@mcp.tool()
async def xiaohongshu_search_tool(keyword: str) -> str:
    """小紅書搜索筆記（需登入）"""
    return await xiaohongshu_search(keyword)


@mcp.tool()
async def xiaohongshu_note_tool(note_id: str) -> str:
    """小紅書筆記詳情（需登入）"""
    return await xiaohongshu_note_detail(note_id)


# ── 抖音 ──

@mcp.tool()
async def douyin_search_tool(keyword: str) -> str:
    """抖音搜索視頻（需登入 + JSVM sandbox ~4s）"""
    return await douyin_search(keyword)


@mcp.tool()
async def douyin_user_tool(user_id: str) -> str:
    """抖音用戶視頻列表（需登入）"""
    return await douyin_user_videos(user_id)


# ── 快手 ──

@mcp.tool()
async def kuaishou_search_tool(keyword: str) -> str:
    """快手搜索視頻（需登入）"""
    return await kuaishou_search(keyword)


@mcp.tool()
async def kuaishou_hot_tool() -> str:
    """快手熱榜（需登入）"""
    return await kuaishou_hot()


# ── 知乎 ──

@mcp.tool()
async def zhihu_hot_tool() -> str:
    """知乎熱榜（需登入）"""
    return await zhihu_hot()


@mcp.tool()
async def zhihu_search_tool(keyword: str) -> str:
    """知乎搜索（需登入）"""
    return await zhihu_search(keyword)


if __name__ == "__main__":
    mcp.run()
