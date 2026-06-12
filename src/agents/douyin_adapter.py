import asyncio
import json
from typing import Optional

from base.platform_base import PlatformAdapter
from src.utils.browser_service import browser
from src.utils.logger import logger

_SEARCH_JS = """\
() => {
    const cards = document.querySelectorAll('.search-result-card');
    return Array.from(cards).map(card => {
        const texts = Array.from(card.querySelectorAll('a, span, p')).map(el => el.textContent.trim()).filter(Boolean);
        const linkEl = card.querySelector('a[href*="/video/"]');
        return {
            title: texts[2] || null,
            author: texts[4] || null,
            duration: texts[0] || null,
            plays: texts[1] || null,
            date: texts[5] || null,
            link: linkEl?.getAttribute('href') ?? null,
        };
    });
}"""

_USER_JS = """\
() => {
    const containers = document.querySelectorAll('a[href*="/video/"]');
    const seen = new Set();
    const items = [];
    containers.forEach(el => {
        const href = el.getAttribute('href');
        if (!href || seen.has(href)) return;
        seen.add(href);
        const titleEl = el.querySelector('[class*="title"], [class*="Title"], h3, h2, p');
        const playEl = el.querySelector('[class*="play"], [class*="Play"], [class*="count"]');
        items.push({
            title: titleEl?.textContent?.trim() ?? null,
            plays: playEl?.textContent?.trim() ?? null,
            link: href ?? null,
        });
    });
    return items;
}"""


async def douyin_search(keyword: str, count: int = 40) -> str:
    """抖音搜索 — Playwright CDP + 网络拦截搜索 API。"""
    logger.info(f"抖音搜索: keyword={keyword} count={count}")
    try:
        page = await browser.new_page()
        try:
            api_items = []
            seen_aweme = set()

            async def on_response(resp):
                if "general/search/single" in resp.url:
                    try:
                        body = await resp.json()
                        data = body.get("data") or []
                        for item in data:
                            info = item.get("aweme_info", item)
                            aid = str(info.get("aweme_id", ""))
                            if not aid or aid in seen_aweme:
                                continue
                            seen_aweme.add(aid)
                            author = info.get("author", {}) or {}
                            stat = info.get("statistics", {}) or {}
                            api_items.append({
                                "title": info.get("desc", ""),
                                "author": author.get("nickname", ""),
                                "plays": stat.get("play_count", 0),
                                "likes": stat.get("digg_count", 0),
                                "aweme_id": aid,
                                "sec_uid": author.get("sec_uid", ""),
                            })
                    except Exception:
                        pass

            page.on("response", lambda resp: asyncio.ensure_future(on_response(resp)))

            await page.goto(f"https://www.douyin.com/search/{keyword}", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(5000)

            max_scrolls = max((count // 10) + 3, 6)
            for _ in range(max_scrolls):
                if len(api_items) >= count:
                    break
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2500)

            # 等待最后一批API响应
            await page.wait_for_timeout(3000)

            result = api_items[:count]
            logger.info(f"抖音搜索完成: {len(result)} 条")
            return json.dumps(result, ensure_ascii=False)
        finally:
            await page.close()
    except Exception as e:
        logger.warning(f"抖音搜索异常: {e}")
        return json.dumps([], ensure_ascii=False)


async def douyin_hot() -> str:
    """爬取抖音熱榜 — 拦截 hot/search/list API。"""
    logger.info("抖音熱榜: 開始爬取")
    try:
        page = await browser.new_page()
        try:
            hot_items = []

            async def on_response(resp):
                if "hot/search/list" in resp.url:
                    try:
                        body = await resp.json()
                        data = body.get("data", {})
                        word_list = data.get("word_list", [])
                        trending_list = data.get("trending_list", [])
                        for item in word_list:
                            word = item.get("word", "")
                            if word:
                                hot_items.append({
                                    "title": word,
                                    "hot_value": item.get("hot_value", ""),
                                    "position": item.get("position", ""),
                                })
                        for item in trending_list:
                            word = item.get("word", "")
                            if word and not any(h.get("title") == word for h in hot_items):
                                hot_items.append({
                                    "title": word,
                                    "hot_value": item.get("hot_value", ""),
                                })
                    except Exception:
                        pass

            page.on("response", lambda resp: asyncio.ensure_future(on_response(resp)))

            await page.goto("https://www.douyin.com/hot", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(8000)

            # 也用 DOM 兜底
            if not hot_items:
                result = await page.evaluate("""() => {
    const items = document.querySelectorAll('[class*="hot"] [class*="title"], [class*="trend"] [class*="title"], [class*="Hot"] [class*="Title"], [class*="HotItem"], [class*="hot-item"]');
    const seen = new Set();
    return Array.from(items).filter(el => {
        const t = el.textContent.trim();
        if (!t || t.length < 3 || seen.has(t)) return false;
        seen.add(t);
        return true;
    }).map(el => ({ title: el.textContent.trim() }));
}""")
                hot_items = list(result) if result else []

            logger.info(f"抖音熱榜完成: {len(hot_items)} 條")
            return json.dumps(hot_items, ensure_ascii=False)
        finally:
            await page.close()
    except Exception as e:
        logger.warning(f"抖音熱榜异常: {e}")
        return json.dumps([], ensure_ascii=False)


async def douyin_detail(video_id: str) -> str:
    """爬取抖音視頻詳情。"""
    logger.info(f"抖音詳情: video_id={video_id}")
    try:
        page = await browser.new_page()
        try:
            await page.goto(f"https://www.douyin.com/video/{video_id}", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(5000)
            result = await page.evaluate("""() => {
    const titleEl = document.querySelector('[class*="title"], [class*="Title"], h1');
    const descEl = document.querySelector('[class*="desc"], [class*="Desc"]');
    const playEl = document.querySelector('[class*="play"], [class*="Play"], [class*="count"]');
    const likeEl = document.querySelector('[class*="like"]:not([class*="digg"])');
    return {
        title: titleEl?.textContent?.trim() || '',
        desc: descEl?.textContent?.trim() || '',
        plays: playEl?.textContent?.trim() || '',
        likes: likeEl?.textContent?.trim() || '',
    };
}""")
            logger.info("抖音詳情完成")
            return json.dumps(result, ensure_ascii=False)
        finally:
            await page.close()
    except Exception as e:
        logger.warning(f"抖音詳情异常: {e}")
        return json.dumps({}, ensure_ascii=False)


async def douyin_comment(video_id: str, count: int = 50) -> str:
    """抖音视频评论 — 拦截 + 主动翻页 comment API。"""
    logger.info(f"抖音評論: video_id={video_id} count={count}")
    try:
        page = await browser.new_page()
        try:
            comments = []
            seen_cids = set()

            async def on_response(resp):
                if "comment/list" in resp.url:
                    try:
                        body = await resp.json()
                        for c in (body.get("comments") or []):
                            cid = str(c.get("cid", ""))
                            if not cid or cid in seen_cids:
                                continue
                            seen_cids.add(cid)
                            user = c.get("user", {}) or {}
                            comments.append({
                                "user": user.get("nickname", ""),
                                "content": c.get("text", ""),
                                "likes": c.get("digg_count", 0),
                                "reply_count": c.get("reply_comment_total", 0),
                            })
                    except Exception:
                        pass

            page.on("response", lambda resp: asyncio.ensure_future(on_response(resp)))

            await page.goto(f"https://www.douyin.com/video/{video_id}", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(5000)

            # 滚动触发首頁评论加载
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.3)")
            await page.wait_for_timeout(3000)

            # 主动翻页获取更多评论
            max_pages = max((count // 20) + 3, 5)
            for page_num in range(max_pages):
                if len(comments) >= count:
                    break
                cursor = page_num * 20
                try:
                    more = await page.evaluate(f"""async () => {{
                        const resp = await fetch("https://www.douyin.com/aweme/v1/web/comment/list/?device_platform=webapp&aid=6383&channel=channel_pc_web&aweme_id={video_id}&cursor={cursor}&count=20");
                        const data = await resp.json();
                        return (data.comments || []).map(c => ({{
                            user: (c.user || {{}}).nickname || '',
                            content: c.text || '',
                            likes: c.digg_count || 0,
                            cid: String(c.cid || ''),
                        }}));
                    }}""")
                    new_count = 0
                    for c in (more or []):
                        cid = c.get("cid", "")
                        if cid and cid not in seen_cids:
                            seen_cids.add(cid)
                            comments.append({
                                "user": c.get("user", ""),
                                "content": c.get("content", ""),
                                "likes": c.get("likes", 0),
                            })
                            new_count += 1
                    if new_count == 0:
                        break
                except Exception:
                    break

                await page.wait_for_timeout(1000)

            result = comments[:count]
            logger.info(f"抖音評論完成: {len(result)} 條")
            return json.dumps(result, ensure_ascii=False)
        finally:
            await page.close()
    except Exception as e:
        logger.warning(f"抖音評論异常: {e}")
        return json.dumps([], ensure_ascii=False)


async def douyin_user_videos(user_id: str) -> str:
    """抖音用户视频 — CDP DOM 抓取."""
    logger.info(f"抖音用戶視頻: user_id={user_id}")
    try:
        page = await browser.new_page()
        try:
            await page.goto(f"https://www.douyin.com/user/{user_id}", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(5000)
            for _ in range(2):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1500)
            result = await page.evaluate(_USER_JS)
            logger.info(f"抖音用戶視頻完成: {len(result)} 條結果")
            return json.dumps(result, ensure_ascii=False)
        finally:
            await page.close()
    except Exception as e:
        logger.warning(f"抖音用戶視頻异常: {e}")
        return json.dumps([], ensure_ascii=False)


class DouyinAdapter(PlatformAdapter):
    _SEARCH_URL = "https://www.douyin.com/search/{keyword}"
    _CARD_SELECTOR = "[class*='search-item'], [class*='video-card'], ul>li"

    @property
    def name(self) -> str:
        return "douyin"

    @property
    def need_login(self) -> bool:
        return True

    async def search(self, keyword: str, limit: Optional[int] = None,
                     sort_type: int = 0, publish_time: int = 0,
                     search_channel: str = "") -> list[dict]:
        try:
            data = json.loads(await douyin_search(keyword, count=limit or 40))
            if data and len(data) > 0:
                return data[:limit] if limit else data
        except Exception as e:
            logger.warning(f"[Douyin] API search failed: {e}, trying adaptive fallback")
        return await self._adaptive_search(keyword, limit)

    async def _adaptive_search(self, keyword: str, limit: Optional[int] = None) -> list[dict]:
        """HTTP 搜索失败时的浏览器兜底搜索。"""
        try:
            if not browser.is_running():
                logger.warning("[Douyin] 浏览器未启动，adaptive 搜索不可用")
                return []
            page = await browser.new_page()
            search_url = f"https://www.douyin.com/search/{keyword}"
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            result = await page.evaluate(_SEARCH_JS)
            return result[:limit] if limit else result
        except Exception as e:
            logger.warning(f"[Douyin] adaptive 搜索失败: {e}")
            return []

    async def hot(self, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await douyin_hot())
        return data[:limit] if limit else data

    async def detail(self, item_id: str, **kwargs) -> dict:
        return json.loads(await douyin_detail(item_id))

    async def comment(self, item_id: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await douyin_comment(item_id, count=limit or 50))
        return data[:limit] if limit else data

    async def user(self, user_id: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await douyin_user_videos(user_id))
        return data[:limit] if limit else data
