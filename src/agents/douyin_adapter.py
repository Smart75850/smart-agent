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
                            video = info.get("video", {}) or {}
                            music = info.get("music", {}) or {}
                            cover_list = (video.get("cover", {}) or {}).get("url_list", [])
                            api_items.append({
                                # 基础信息
                                "title": info.get("desc", ""),
                                "aweme_id": aid,
                                "create_time": info.get("create_time", 0),
                                "duration_ms": video.get("duration", 0),
                                "resolution": f"{video.get('width', 0)}x{video.get('height', 0)}",
                                "cover_url": cover_list[0] if cover_list else "",
                                "media_type": info.get("media_type", 0),
                                # 作者信息
                                "author": author.get("nickname", ""),
                                "author_uid": author.get("uid", ""),
                                "author_sec_uid": author.get("sec_uid", ""),
                                "author_followers": author.get("follower_count", 0),
                                "author_following": author.get("following_count", 0),
                                "author_avatar": (author.get("avatar_thumb", {}) or {}).get("url_list", [""])[0] if isinstance(author.get("avatar_thumb"), dict) else "",
                                # 统计数据
                                "plays": stat.get("play_count", 0),
                                "likes": stat.get("digg_count", 0),
                                "comments": stat.get("comment_count", 0),
                                "shares": stat.get("share_count", 0),
                                "collects": stat.get("collect_count", 0),
                                "downloads": stat.get("download_count", 0),
                                "forwards": stat.get("forward_count", 0),
                                # 音乐信息
                                "music_title": music.get("title", ""),
                                "music_author": music.get("author", ""),
                                "music_id": str(music.get("id", "")),
                                # 分享信息
                                "share_url": (info.get("share_info", {}) or {}).get("share_url", ""),
                                # 标签
                                "hashtags": [t.get("hashtag_name", "") for t in (info.get("text_extra", []) or []) if t.get("hashtag_name")],
                            })
                    except Exception:
                        pass

            page.on("response", lambda resp: asyncio.ensure_future(on_response(resp)))

            await page.goto(f"https://www.douyin.com/search/{keyword}", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(5000)

            # 登录墙检测
            page_text = await page.evaluate("() => document.body?.innerText || ''")
            if "请先登录" in page_text or "登录" in page_text:
                logger.warning("抖音搜索: 检测到登录墙，请先在浏览器中登录抖音账号")
                return json.dumps([], ensure_ascii=False)

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
    """爬取抖音视频详情 — 拦截 detail API 获取播放量等完整统计（搜索API中play_count为0）。"""
    logger.info(f"抖音详情: video_id={video_id}")
    try:
        page = await browser.new_page()
        try:
            detail_data = {}

            async def on_response(resp):
                nonlocal detail_data
                if "aweme/v1/web/aweme/detail" in resp.url and not detail_data:
                    try:
                        body = await resp.json()
                        info = (body.get("aweme_detail") or {})
                        author = info.get("author", {}) or {}
                        stat = info.get("statistics", {}) or {}
                        video = info.get("video", {}) or {}
                        cover_list = (video.get("cover", {}) or {}).get("url_list", [])
                        detail_data = {
                            "title": info.get("desc", ""),
                            "aweme_id": str(info.get("aweme_id", "")),
                            "create_time": info.get("create_time", 0),
                            "duration_ms": video.get("duration", 0),
                            "resolution": f"{video.get('width', 0)}x{video.get('height', 0)}",
                            "cover_url": cover_list[0] if cover_list else "",
                            "author": author.get("nickname", ""),
                            "author_uid": author.get("uid", ""),
                            "author_followers": author.get("follower_count", 0),
                            "plays": stat.get("play_count", 0),
                            "likes": stat.get("digg_count", 0),
                            "comments": stat.get("comment_count", 0),
                            "shares": stat.get("share_count", 0),
                            "collects": stat.get("collect_count", 0),
                            "forwards": stat.get("forward_count", 0),
                            "downloads": stat.get("download_count", 0),
                            "share_url": (info.get("share_info", {}) or {}).get("share_url", ""),
                            "hashtags": [t.get("hashtag_name", "") for t in (info.get("text_extra", []) or []) if t.get("hashtag_name")],
                        }
                    except Exception:
                        pass

            page.on("response", lambda resp: asyncio.ensure_future(on_response(resp)))
            await page.goto(f"https://www.douyin.com/video/{video_id}", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(5000)

            # DOM 兜底（API未拦截到时）
            if not detail_data:
                result = await page.evaluate("""() => {
    const titleEl = document.querySelector('[class*=\"title\"], [class*=\"Title\"], h1');
    const descEl = document.querySelector('[class*=\"desc\"], [class*=\"Desc\"]');
    return { title: titleEl?.textContent?.trim() || '', desc: descEl?.textContent?.trim() || '' };
}""")
                detail_data = result

            logger.info("抖音详情完成")
            return json.dumps(detail_data, ensure_ascii=False)
        finally:
            await page.close()
    except Exception as e:
        logger.warning(f"抖音详情异常: {e}")
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
                                "cid": str(c.get("cid", "")),
                                "user": user.get("nickname", ""),
                                "user_uid": user.get("uid", ""),
                                "user_avatar": (user.get("avatar_thumb", {}) or {}).get("url_list", [""])[0] if isinstance(user.get("avatar_thumb"), dict) else "",
                                "content": c.get("text", ""),
                                "likes": c.get("digg_count", 0),
                                "reply_count": c.get("reply_comment_total", 0),
                                "create_time": c.get("create_time", 0),
                                "reply_id": c.get("reply_id", ""),
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
                                "cid": cid,
                                "user": c.get("user", ""),
                                "content": c.get("content", ""),
                                "likes": c.get("likes", 0),
                                "reply_count": c.get("reply_count", 0),
                                "create_time": c.get("create_time", 0),
                            })
                            new_count += 1
                    if new_count == 0:
                        break
                except Exception:
                    break

                await page.wait_for_timeout(1000)

            # DOM 兜底（API 拦截为空时，直接从页面提取评论）
            if not comments:
                dom_result = await page.evaluate("""() => {
    const items = document.querySelectorAll('[class*="comment-item"], [class*="CommentItem"], .comment-item, [class*="comment"], [class*="Comment"]');
    const seen = new Set();
    const out = [];
    items.forEach(item => {
        const t = item.textContent.trim();
        if (!t || t.length < 3 || seen.has(t)) return;
        seen.add(t);
        const contentEl = item.querySelector('[class*="content"], [class*="text"], .content, .text, p');
        const userEl = item.querySelector('[class*="user"], [class*="name"], [class*="author"], [class*="nickname"]');
        out.push({
            user: userEl?.textContent?.trim() || '',
            content: contentEl?.textContent?.trim() || t.slice(0, 200),
            likes: 0,
        });
    });
    if (out.length < 5) {
        const allText = document.body?.innerText || '';
        const lines = allText.split('\\n').filter(l => l.trim().length > 10).slice(0, 40);
        for (const l of lines) {
            const t = l.trim().slice(0, 200);
            if (t && !seen.has(t)) { seen.add(t); out.push({user: '', content: t, likes: 0}); }
        }
    }
    return out;
}""")
                if dom_result:
                    comments = dom_result
                    logger.info("抖音評論: API 拦截为空，使用 DOM 兜底")

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
            if not browser.is_running:
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
