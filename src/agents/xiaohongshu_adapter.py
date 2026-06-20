import asyncio
import json
from pathlib import Path
from typing import Optional

from base.platform_base import PlatformAdapter
from src.utils.browser_service import browser
from src.utils.logger import logger


_SEARCH_JS = """\
() => {
    const out = []; const seen = new Set();
    const cards = document.querySelectorAll('.note-item, [class*="note-item"], [class*="NoteItem"], section a[href*="/explore/"], [class*="feeds-page"] a[href*="/explore/"], a[href*="/search_result/"]');
    cards.forEach(el => {
        const linkEl = el.tagName === 'A' ? el : el.querySelector('a[href*="/explore/"], a[href*="/search_result/"]');
        const href = linkEl?.getAttribute('href') || '';
        if (!href || seen.has(href)) return;
        seen.add(href);
        const title = el.querySelector('.title, [class*="title"], [class*="note-title"]')?.textContent?.trim()
            || el.querySelector('span')?.textContent?.trim()
            || el.textContent.trim().slice(0, 80);
        const author = el.querySelector('.author, .name, [class*="author"], [class*="name"]')?.textContent?.trim() || '';
        const likes = el.querySelector('.like, [class*="like"], [class*="count"], [class*="engage"]')?.textContent?.trim() || '';
        if (title.length > 3) out.push({title: title, author: author, likes: likes, link: href});
    });
    if (out.length === 0) {
        document.querySelectorAll('a[href*="/explore/"]').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (!href || seen.has(href)) return;
            seen.add(href);
            const t = a.textContent.trim();
            if (t.length > 5) out.push({title: t.slice(0, 100), author: '', likes: '', link: href});
        });
    }
    return out;
}"""

_DETAIL_JS = """\
() => {
    const titleEl = document.querySelector('.title, #detail-title, .note-title, [class*="note-title"], [class*="detail-title"]');
    const descEl = document.querySelector('.desc, .content, .note-content, [class*="desc"], [class*="note-content"], [class*="content"]');
    const authorEl = document.querySelector('.author, .name, .username, .note-author, [class*="author"], [class*="note-author"]');
    const likeEl = document.querySelector('.like, .engage-bar .like, [class*="like"], [class*="engage"]');
    const collectEl = document.querySelector('.collect, .engage-bar .collect, [class*="collect"]');
    const commentEl = document.querySelector('.comment, .engage-bar .comment, [class*="comment"]');
    return {
        title: titleEl?.textContent?.trim() ?? null,
        desc: descEl?.textContent?.trim() ?? null,
        author: authorEl?.textContent?.trim() ?? null,
        likes: likeEl?.textContent?.trim() ?? null,
        collects: collectEl?.textContent?.trim() ?? null,
        comments: commentEl?.textContent?.trim() ?? null,
    };
}"""


async def xiaohongshu_search(keyword: str, count: int = 40) -> str:
    """搜索小红书笔记 — CDP 浏览器拦截搜索 API + DOM 兜底。需登入。回传 JSON 字串。"""
    logger.info(f"小红书搜索: keyword={keyword} count={count}")
    try:
        page = await browser.new_page()
        try:
            api_items: list[dict] = []
            seen_ids: set[str] = set()

            async def on_response(resp):
                """拦截搜索 API 响应，提取完整字段（比 DOM 多图片数/笔记类型等）。"""
                if "search/notes" in resp.url and resp.status == 200:
                    try:
                        body = await resp.json()
                        items = body.get("data", {}).get("items", []) or []
                        for item in items:
                            note_card = item.get("note_card") or item
                            note_id = str(item.get("id", "") or note_card.get("note_id", ""))
                            if not note_id or note_id in seen_ids:
                                continue
                            seen_ids.add(note_id)
                            user = note_card.get("user", {}) or {}
                            interact = note_card.get("interact_info", {}) or {}
                            cover = note_card.get("cover", {}) or {}
                            image_list = note_card.get("image_list", []) or []
                            api_items.append({
                                "note_id": note_id,
                                "title": note_card.get("display_title", ""),
                                "desc": (note_card.get("desc", "") or "").strip(),
                                "type": note_card.get("type", "normal"),
                                "author": user.get("nickname", ""),
                                "author_id": user.get("user_id", ""),
                                "author_avatar": user.get("avatar", ""),
                                "likes": interact.get("liked_count", ""),
                                "collects": interact.get("collected_count", ""),
                                "comments": interact.get("comment_count", ""),
                                "shares": interact.get("share_count", ""),
                                "cover_url": cover.get("url_default", "") or cover.get("url", ""),
                                "url": f"https://www.xiaohongshu.com/explore/{note_id}",
                                "image_count": len(image_list),
                                "tag_list": [t.get("name", "") for t in (note_card.get("tag_list", []) or []) if t.get("name")],
                            })
                    except Exception:
                        pass

            page.on("response", lambda resp: asyncio.ensure_future(on_response(resp)))

            search_url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}&source=web_search_result_notes"
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)

            # 检查登录墙
            body_text = await page.evaluate("() => document.body.textContent.substring(0, 500)")
            if "登录后查看" in body_text:
                logger.warning("小红书未登录，请先在 CDP Chrome 中扫码登录小红书")
                return json.dumps([], ensure_ascii=False)

            # 滚动触发搜索 API 分页加载
            max_scrolls = max((count // 20) + 3, 5)
            for _ in range(max_scrolls):
                if len(api_items) >= count:
                    break
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2500)

            # 等待最后一波 API 响应
            await page.wait_for_timeout(2000)

            # DOM 兜底（API 未拦截到时用 CSS 选择器抓取）
            if not api_items:
                dom_result = await page.evaluate(_SEARCH_JS)
                if dom_result:
                    api_items = dom_result
                    logger.info("小红书搜索: API 拦截为空，使用 DOM 兜底")

            result = api_items[:count]
            logger.info(f"小红书搜索完成: {len(result)} 条")
            return json.dumps(result, ensure_ascii=False)
        finally:
            await page.close()
    except Exception as e:
        logger.warning(f"小红书搜索异常: {e}")
        return json.dumps([], ensure_ascii=False)


async def xiaohongshu_note_detail(note_id: str) -> str:
    """獲取小紅薯筆記詳情，需登入先有完整內容。回傳 JSON 字串。"""
    logger.info(f"小紅薯詳情: note_id={note_id}")
    url = f"https://www.xiaohongshu.com/explore/{note_id}"
    result = await browser.evaluate(url, _DETAIL_JS)
    title = result.get("title", "N/A") if isinstance(result, dict) else "N/A"
    logger.info(f"小紅薯詳情完成: {title}")
    return json.dumps(result, ensure_ascii=False)


async def xiaohongshu_comment(note_id: str, count: int = 50) -> str:
    """爬取小红书笔记评论 — CDP 浏览器拦截评论 API + DOM 兜底。需登入。回传 JSON 字串。"""
    logger.info(f"小红书评论: note_id={note_id} count={count}")
    try:
        page = await browser.new_page()
        try:
            comments: list[dict] = []
            seen_cids: set[str] = set()

            async def on_response(resp):
                """拦截评论 API 响应，提取结构化字段。"""
                if ("comment" in resp.url or "sub_comment" in resp.url) and resp.status == 200:
                    try:
                        body = await resp.json()
                        comment_list = (body.get("data", {}).get("comments", []) or [])
                        for c in comment_list:
                            cid = str(c.get("id", ""))
                            if not cid or cid in seen_cids:
                                continue
                            seen_cids.add(cid)
                            user = c.get("user_info", {}) or {}
                            # 子评论
                            sub_comments = []
                            for sc in (c.get("sub_comments", []) or []):
                                sc_user = sc.get("user_info", {}) or {}
                                sub_comments.append({
                                    "content": sc.get("content", ""),
                                    "user": sc_user.get("nickname", ""),
                                    "likes": sc.get("like_count", 0),
                                })
                            comments.append({
                                "cid": cid,
                                "content": c.get("content", ""),
                                "user": user.get("nickname", ""),
                                "user_id": user.get("user_id", ""),
                                "user_avatar": user.get("avatar", ""),
                                "likes": c.get("like_count", 0),
                                "reply_count": c.get("sub_comment_count", 0),
                                "create_time": c.get("create_time", 0),
                                "sub_comments": sub_comments,
                            })
                    except Exception:
                        pass

            page.on("response", lambda resp: asyncio.ensure_future(on_response(resp)))

            url = f"https://www.xiaohongshu.com/explore/{note_id}"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)

            # 滚动触发评论加载
            for _ in range(max((count // 20) + 3, 5)):
                if len(comments) >= count:
                    break
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1500)

            # 等待最后一波 API 响应
            await page.wait_for_timeout(2000)

            # DOM 兜底
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
        out.push({
            content: contentEl?.textContent?.trim() || t.slice(0, 200),
            replies: Array.from(item.querySelectorAll('[class*="reply-item"], [class*="ReplyItem"], .reply-item, [class*="sub"]')).map(r => ({
                content: r.querySelector('[class*="text"], [class*="content"], p')?.textContent?.trim() || r.textContent.trim().slice(0, 200),
            })),
        });
    });
    if (out.length < 8) {
        const allText = document.body?.innerText || '';
        const lines = allText.split('\\n').filter(l => l.trim().length > 10).slice(0, 60);
        for (const l of lines) {
            const t = l.trim().slice(0, 200);
            if (t && !seen.has(t)) { seen.add(t); out.push({content: t, replies: []}); }
        }
    }
    return out;
}""")
                if dom_result:
                    comments = dom_result
                    logger.info("小红书评论: API 拦截为空，使用 DOM 兜底")

            result = comments[:count]
            logger.info(f"小红书评论完成: {len(result)} 条")
            return json.dumps(result, ensure_ascii=False)
        finally:
            await page.close()
    except Exception as e:
        logger.warning(f"小红书评论异常: {e}")
        return json.dumps([], ensure_ascii=False)


async def xiaohongshu_hot() -> str:
    """爬取小紅薯推薦 feed（近似熱榜），需登入先有內容。回傳 JSON 字串。"""
    logger.info("小紅薯熱榜: 開始爬取")
    page = await browser.new_page()
    try:
        await page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        result = await page.evaluate("""() => {
    const items = document.querySelectorAll('.note-item, [class*="note-item"], [class*="feed"] [class*="item"]');
    const seen = new Set();
    return Array.from(items).filter(el => {
        const t = el.textContent.trim();
        if (!t || t.length < 5 || seen.has(t)) return false;
        seen.add(t);
        return true;
    }).slice(0, 30).map(el => ({
        title: el.querySelector('.title, [class*="title"]')?.textContent?.trim() || '',
        likes: el.querySelector('.like, [class*="like"], [class*="count"]')?.textContent?.trim() || '',
        link: el.querySelector('a')?.getAttribute('href') || '',
    }));
}""")
        logger.info(f"小紅薯熱榜完成: {len(result)} 條")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


async def xiaohongshu_user(user_id: str) -> str:
    """爬取小紅薯用戶主頁筆記列表，需登入先有內容。回傳 JSON 字串。"""
    logger.info(f"小紅薯用戶: user_id={user_id}")
    page = await browser.new_page()
    try:
        await page.goto(f"https://www.xiaohongshu.com/user/profile/{user_id}", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        result = await page.evaluate("""() => {
    const items = document.querySelectorAll('.note-item, [class*="note-item"]');
    const seen = new Set();
    return Array.from(items).filter(el => {
        const t = el.textContent.trim();
        if (!t || t.length < 3 || seen.has(t)) return false;
        seen.add(t);
        return true;
    }).slice(0, 30).map(el => ({
        title: el.querySelector('.title, [class*="title"]')?.textContent?.trim() || '',
        likes: el.querySelector('.like, [class*="like"], [class*="count"]')?.textContent?.trim() || '',
        link: el.querySelector('a')?.getAttribute('href') || '',
    }));
}""")
        logger.info(f"小紅薯用戶完成: {len(result)} 條")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


class XiaohongshuAdapter(PlatformAdapter):
    _SEARCH_URL = "https://www.xiaohongshu.com/search_result?keyword={keyword}"
    _CARD_SELECTOR = ".note-item, .feeds-page .note-item, [class*='note-item'], section.note-item"

    @property
    def name(self) -> str:
        return "xiaohongshu"

    @property
    def need_login(self) -> bool:
        return True

    async def search(self, keyword: str, limit: Optional[int] = None,
                     sort_type: int = 0, publish_time: int = 0,
                     search_channel: str = "") -> list[dict]:
        try:
            data = json.loads(await xiaohongshu_search(keyword, count=limit or 40))
            if data and len(data) > 0:
                return data[:limit] if limit else data
        except Exception as e:
            logger.warning(f"[Xiaohongshu] API search failed: {e}, trying adaptive fallback")
        return await self._adaptive_search(keyword, limit)

    async def _adaptive_search(self, keyword: str, limit: Optional[int] = None) -> list[dict]:
        """HTTP 搜索失败时的浏览器兜底搜索。"""
        try:
            if not browser.is_running():
                logger.warning("[Xiaohongshu] 浏览器未启动，adaptive 搜索不可用")
                return []
            page = await browser.new_page()
            search_url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}"
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            result = await page.evaluate(_SEARCH_JS)
            return result[:limit] if limit else result
        except Exception as e:
            logger.warning(f"[Xiaohongshu] adaptive 搜索失败: {e}")
            return []

    async def hot(self, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await xiaohongshu_hot())
        return data[:limit] if limit else data

    async def detail(self, item_id: str, xsec_token: str = "", **kwargs) -> dict:
        return json.loads(await xiaohongshu_note_detail(item_id))

    async def comment(self, item_id: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await xiaohongshu_comment(item_id, count=limit or 50))
        return data[:limit] if limit else data

    async def user(self, user_id: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await xiaohongshu_user(user_id))
        return data[:limit] if limit else data
