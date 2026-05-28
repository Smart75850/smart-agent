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


def _parse_cn_num(value) -> int:
    """解析中文格式化数字如 '184.3万' '1.5亿' '4,567' 为整数。"""
    s = str(value or 0).replace(",", "").replace("，", "").strip()
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


def _normalize(item: dict, platform: str) -> dict:
    """归一化单个条目到统一字段。含中文数字→整数 + heat→plays fallback。"""
    out = {"platform": platform}
    for target, sources in _FIELD_MAP.items():
        for src in sources:
            val = item.get(src)
            if val is not None and val != "":
                out[target] = str(val)
                break
        if target not in out:
            out[target] = ""

    # 中文数字转整数 (plays/likes/comments/duration 字段)
    for num_field in ("plays", "likes", "comments"):
        raw = out.get(num_field, "")
        if raw and any(c in str(raw) for c in "亿万wk,，"):
            out[num_field] = str(_parse_cn_num(raw))

    # plays fallback: heat / replies (不含 hot_value — 热搜热度值≠播放量)
    if not out.get("plays") or out["plays"] == "0":
        for fb in ("heat", "replies", "reply_count", "reads_count"):
            v = item.get(fb, "")
            if v and str(v).strip():
                out["plays"] = str(v).strip()
                break

    # link fallback: 构造搜索链接
    if not out.get("link") or out["link"] == "":
        title = out.get("title", "")
        if title:
            import urllib.parse
            q = urllib.parse.quote(title)
            link_tpl = {
                "douyin": f"https://www.douyin.com/search/{q}",
                "xiaohongshu": f"https://www.xiaohongshu.com/search_result?keyword={q}",
                "zhihu": f"https://www.zhihu.com/search?type=content&q={q}",
                "weibo": f"https://s.weibo.com/weibo?q={q}",
                "kuaishou": f"https://www.kuaishou.com/search/video?searchKey={q}",
                "bilibili": f"https://search.bilibili.com/all?keyword={q}",
                "tieba": f"https://tieba.baidu.com/f/search/res?qw={q}",
            }
            out["link"] = link_tpl.get(platform, "")

    out["platform_id"] = (
        item.get("photo_id") or item.get("bvid") or item.get("aweme_id")
        or item.get("aid") or item.get("note_id") or item.get("question_id")
        or item.get("weibo_id") or item.get("tid")
        or item.get("platform_id") or item.get("id") or ""
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