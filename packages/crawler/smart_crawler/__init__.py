"""
Smart Crawler — 多平台内容采集
================================
一行 import，7 平台即刻用得。

Usage:
    from smart_crawler import search
    items = search("xiaohongshu", "穿搭", limit=10)

    from smart_crawler import XiaohongshuCrawler
    xhs = XiaohongshuCrawler()
    hot = xhs.hot()
    detail = xhs.detail("note_id", xsec_token="token")
"""

import os as _os
import sys as _sys

# 自动找到 smart-agent 项目根目录
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

from src.utils.browser_service import browser as _browser

__version__ = "0.1.0"

# ============================================================
#  统一搜索接口
# ============================================================

# 注意：本文件属于独立发布包（smart-crawler），必须自包含，不能 import 主项目 constant/platform_registry。
# 平台列表如有增删，需同步更新主项目 constant/platform_registry.py 与本处。
PLATFORMS = ["bilibili", "xiaohongshu", "douyin", "zhihu", "kuaishou", "weibo", "tieba"]

async def search(platform: str, keyword: str, limit: int = 20, **kwargs):
    """统一搜索接口——一个函数搜全部平台。

    Args:
        platform: bilibili/xiaohongshu/douyin/zhihu/kuaishou/weibo/tieba
        keyword: 搜索关键词
        limit: 返回条数
    Returns:
        list[dict]: 搜索结果
    """
    adapter = _get_adapter(platform)
    return await adapter.search(keyword, limit=limit, **kwargs)

async def hot(platform: str, limit: int = 20):
    """热榜"""
    adapter = _get_adapter(platform)
    return await adapter.hot(limit=limit)

async def detail(platform: str, item_id: str, **kwargs):
    """详情"""
    adapter = _get_adapter(platform)
    return await adapter.detail(item_id, **kwargs)

async def comment(platform: str, item_id: str, limit: int = 20, **kwargs):
    """评论"""
    adapter = _get_adapter(platform)
    return await adapter.comment(item_id, limit=limit, **kwargs)

async def user(platform: str, user_id: str, limit: int = 20):
    """用户作品"""
    adapter = _get_adapter(platform)
    return await adapter.user(user_id, limit=limit)

async def start_browser(engine: str = "auto"):
    """启动浏览器。engine: auto/cdp/playwright"""
    if engine != "auto":
        _os.environ["BROWSER_ENGINE"] = engine
    await _browser.start()

async def close_browser():
    """关闭浏览器"""
    await _browser.close()

# ============================================================
#  平台专属类
# ============================================================

class BilibiliCrawler:
    def __init__(self): self._a = _get_adapter("bilibili")
    async def search(self, keyword, limit=20): return await self._a.search(keyword, limit=limit)
    async def hot(self, limit=20): return await self._a.hot(limit=limit)
    async def detail(self, bvid): return await self._a.detail(bvid)
    async def comment(self, bvid, limit=20): return await self._a.comment(bvid, limit=limit)
    async def user(self, uid, limit=20): return await self._a.user(uid, limit=limit)

class XiaohongshuCrawler:
    def __init__(self): self._a = _get_adapter("xiaohongshu")
    async def search(self, keyword, limit=20): return await self._a.search(keyword, limit=limit)
    async def hot(self, limit=20): return await self._a.hot(limit=limit)
    async def detail(self, note_id, xsec_token=""): return await self._a.detail(note_id, xsec_token=xsec_token)
    async def comment(self, note_id, limit=20, xsec_token=""): return await self._a.comment(note_id, limit=limit, xsec_token=xsec_token)
    async def user(self, user_id, limit=20): return await self._a.user(user_id, limit=limit)

class DouyinCrawler:
    def __init__(self): self._a = _get_adapter("douyin")
    async def search(self, keyword, limit=20): return await self._a.search(keyword, limit=limit)
    async def hot(self, limit=20): return await self._a.hot(limit=limit)
    async def detail(self, video_id): return await self._a.detail(video_id)
    async def comment(self, video_id, limit=20): return await self._a.comment(video_id, limit=limit)
    async def user(self, user_id, limit=20): return await self._a.user(user_id, limit=limit)

class ZhihuCrawler:
    def __init__(self): self._a = _get_adapter("zhihu")
    async def search(self, keyword, limit=20): return await self._a.search(keyword, limit=limit)
    async def hot(self, limit=20): return await self._a.hot(limit=limit)
    async def detail(self, qid): return await self._a.detail(qid)
    async def comment(self, qid, limit=20): return await self._a.comment(qid, limit=limit)
    async def user(self, uid, limit=20): return await self._a.user(uid, limit=limit)

class KuaishouCrawler:
    def __init__(self): self._a = _get_adapter("kuaishou")
    async def search(self, keyword, limit=20): return await self._a.search(keyword, limit=limit)
    async def hot(self, limit=20): return await self._a.hot(limit=limit)
    async def detail(self, vid): return await self._a.detail(vid)
    async def comment(self, vid, limit=20): return await self._a.comment(vid, limit=limit)
    async def user(self, uid, limit=20): return await self._a.user(uid, limit=limit)

class WeiboCrawler:
    def __init__(self): self._a = _get_adapter("weibo")
    async def search(self, keyword, limit=20): return await self._a.search(keyword, limit=limit)
    async def hot(self, limit=20): return await self._a.hot(limit=limit)
    async def detail(self, wid): return await self._a.detail(wid)
    async def comment(self, wid, limit=20): return await self._a.comment(wid, limit=limit)
    async def user(self, uid, limit=20): return await self._a.user(uid, limit=limit)

class TiebaCrawler:
    def __init__(self): self._a = _get_adapter("tieba")
    async def search(self, keyword, limit=20): return await self._a.search(keyword, limit=limit)
    async def hot(self, limit=20): return await self._a.hot(limit=limit)
    async def detail(self, tid): return await self._a.detail(tid)
    async def comment(self, tid, limit=20): return await self._a.comment(tid, limit=limit)
    async def user(self, uid, limit=20): return await self._a.user(uid, limit=limit)

# ============================================================
#  Internal
# ============================================================

def _get_adapter(platform: str):
    if platform == "bilibili":
        from src.agents.bilibili_adapter import BilibiliAdapter
        return BilibiliAdapter()
    elif platform == "xiaohongshu":
        from src.agents.xiaohongshu_adapter import XiaohongshuAdapter
        return XiaohongshuAdapter()
    elif platform == "douyin":
        from src.agents.douyin_adapter import DouyinAdapter
        return DouyinAdapter()
    elif platform == "zhihu":
        from src.agents.zhihu_adapter import ZhihuAdapter
        return ZhihuAdapter()
    elif platform == "kuaishou":
        from src.agents.kuaishou_adapter import KuaishouAdapter
        return KuaishouAdapter()
    elif platform == "weibo":
        from src.agents.weibo_adapter import WeiboAdapter
        return WeiboAdapter()
    elif platform == "tieba":
        from src.agents.tieba_adapter import TiebaAdapter
        return TiebaAdapter()
    raise ValueError(f"Unsupported platform: {platform}")
