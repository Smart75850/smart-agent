"""跨平台聚合器 — 统一搜多平台，归一化输出。"""
import hashlib

from src.utils.logger import logger


_FIELD_MAP = {
    "title":     ("title", "caption", "desc", "subject", "name"),
    "author":    ("author", "owner", "user", "nickname", "author_name", "screen_name"),
    "plays":     ("plays", "view_count", "viewCount", "play_count", "views", "reads_count"),
    "likes":     ("likes", "like_count", "likeCount", "digg_count", "votes", "attitudes_count", "favorites"),
    "link":      ("link", "url", "share_url", "short_url", "href"),
    "cover_url": ("cover_url", "cover", "coverUrl", "pic_url", "pic", "image_url"),
    "excerpt":   ("excerpt", "summary", "content", "description", "abstract"),
    "comments":  ("comments", "comment_count", "replies", "reply_count", "reposts_count"),
    "duration":  ("duration", "length", "video_duration"),
}


def _normalize(item: dict, platform: str) -> dict:
    """归一化单个条目到统一字段。"""
    out = {"platform": platform}
    for target, sources in _FIELD_MAP.items():
        for src in sources:
            val = item.get(src)
            if val is not None and val != "":
                out[target] = str(val)
                break
        if target not in out:
            out[target] = ""
    out["platform_id"] = (
        item.get("photo_id") or item.get("bvid") or item.get("aweme_id")
        or item.get("aid") or item.get("note_id") or item.get("question_id")
        or item.get("weibo_id") or item.get("tid")
        or item.get("id") or ""
    )
    out["raw"] = item
    return out


async def aggregate_search(keyword: str, limit: int = 30, use_orchestrator: bool = False) -> list[dict]:
    """同时搜索 5 个平台，归一化后合并。"""
    if use_orchestrator:
        from src.orchestrator import run_pipeline
        return await run_pipeline(keyword, limit=limit)

    from src.agents.bilibili_adapter import BilibiliAdapter
    from src.agents.xiaohongshu_adapter import XiaohongshuAdapter
    from src.agents.douyin_adapter import DouyinAdapter
    from src.agents.zhihu_adapter import ZhihuAdapter
    from src.agents.kuaishou_adapter import KuaishouAdapter

    adapters = [
        ("bilibili", BilibiliAdapter()),
        ("xiaohongshu", XiaohongshuAdapter()),
        ("douyin", DouyinAdapter()),
        ("zhihu", ZhihuAdapter()),
        ("kuaishou", KuaishouAdapter()),
    ]

    results = []
    for platform, adapter in adapters:
        try:
            items = await adapter.search(keyword, limit=limit)
            normalized = [_normalize(item, platform) for item in items]
            results.extend(normalized)
            logger.info(f"聚合 [{platform}]: {len(normalized)} 条")
        except Exception as e:
            logger.warning(f"聚合 [{platform}] 失败: {e}")

    results.sort(key=lambda x: len(x.get("plays", "") or x.get("likes", "")), reverse=True)
    return results


async def aggregate_hot(limit: int = 20, use_orchestrator: bool = False) -> list[dict]:
    """聚合 5 平台热榜。"""
    if use_orchestrator:
        from src.orchestrator import run_pipeline
        return await run_pipeline("", limit=limit)

    from src.agents.bilibili_adapter import BilibiliAdapter
    from src.agents.xiaohongshu_adapter import XiaohongshuAdapter
    from src.agents.douyin_adapter import DouyinAdapter
    from src.agents.zhihu_adapter import ZhihuAdapter
    from src.agents.kuaishou_adapter import KuaishouAdapter

    adapters = [
        ("bilibili", BilibiliAdapter()),
        ("xiaohongshu", XiaohongshuAdapter()),
        ("douyin", DouyinAdapter()),
        ("zhihu", ZhihuAdapter()),
        ("kuaishou", KuaishouAdapter()),
    ]

    results = []
    for platform, adapter in adapters:
        try:
            items = await adapter.hot(limit=limit)
            normalized = [_normalize(item, platform) for item in items]
            results.extend(normalized)
            logger.info(f"聚合热榜 [{platform}]: {len(normalized)} 条")
        except Exception as e:
            logger.warning(f"聚合热榜 [{platform}] 失败: {e}")

    return results