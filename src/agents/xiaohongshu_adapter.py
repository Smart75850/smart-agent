import asyncio
import json
import re
from typing import Optional

from base.platform_base import PlatformAdapter
from src.agents.base_adapter import JsonAdapterMixin
from src.utils.browser_service import browser
from src.utils.logger import logger


_SEARCH_JS = r"""() => {
    const out = []; const seen = new Set();
    const cards = document.querySelectorAll('.note-item, [class*="note-item"], [class*="NoteItem"], section a[href*="/explore/"], [class*="feeds-page"] a[href*="/explore/"], a[href*="/search_result/"]');
    const parseHref = (href) => {
        if (!href) return {note_id: '', xsec_token: ''};
        // 提取 note_id: /explore/xxxx 或 /search_result/xxxx
        const m = href.match(/\/(explore|search_result)\/([a-zA-Z0-9]+)/);
        const note_id = m ? m[2] : '';
        // 提取 xsec_token
        const xm = href.match(/xsec_token=([^&]+)/);
        const xsec_token = xm ? xm[1] : '';
        return {note_id, xsec_token};
    };
    cards.forEach(el => {
        const linkEl = el.tagName === 'A' ? el : el.querySelector('a[href*="/explore/"], a[href*="/search_result/"]');
        const href = linkEl?.getAttribute('href') || '';
        if (!href || seen.has(href)) return;
        seen.add(href);
        const {note_id, xsec_token} = parseHref(href);
        const title = el.querySelector('.title, [class*="title"], [class*="note-title"]')?.textContent?.trim()
            || el.querySelector('span')?.textContent?.trim()
            || el.textContent.trim().slice(0, 80);
        const author = el.querySelector('.author, .name, [class*="author"], [class*="name"]')?.textContent?.trim() || '';
        const likes = el.querySelector('.like, [class*="like"], [class*="count"], [class*="engage"]')?.textContent?.trim() || '';
        const coverEl = el.querySelector('img');
        const cover_url = coverEl?.getAttribute('src') || coverEl?.getAttribute('data-src') || '';
        const detail_url = note_id ? ('https://www.xiaohongshu.com/explore/' + note_id + (xsec_token ? '?xsec_token=' + xsec_token + '&xsec_source=pc_search' : '')) : href;
        if (title.length > 3) out.push({note_id, xsec_token, title, author, likes, cover_url, url: detail_url});
    });
    if (out.length === 0) {
        document.querySelectorAll('a[href*="/explore/"]').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (!href || seen.has(href)) return;
            seen.add(href);
            const {note_id, xsec_token} = parseHref(href);
            const t = a.textContent.trim();
            const detail_url = note_id ? ('https://www.xiaohongshu.com/explore/' + note_id + (xsec_token ? '?xsec_token=' + xsec_token + '&xsec_source=pc_search' : '')) : href;
            if (t.length > 5) out.push({note_id, xsec_token, title: t.slice(0, 100), author: '', likes: '', cover_url: '', url: detail_url});
        });
    }
    return out;
}"""

_DETAIL_JS = r"""() => {
    // 优先从 __INITIAL_STATE__ 提取完整数据（SSR 内嵌）
    try {
        const state = window.__INITIAL_STATE__;
        if (state && state.note && state.note.noteDetailMap) {
            const map = state.note.noteDetailMap;
            const noteId = Object.keys(map)[0];
            const note = map[noteId] && map[noteId].note;
            if (note) {
                const user = note.user || {};
                const interact = note.interactInfo || {};
                const images = (note.imageList || []).map(img => img.urlDefault || img.url || '');
                const tags = (note.tagList || []).map(t => t.name || '');
                return {
                    title: note.title || '',
                    desc: note.desc || '',
                    full_text: note.desc || '',
                    author: user.nickname || '',
                    author_id: user.userId || '',
                    author_avatar: user.avatar || '',
                    likes: interact.likedCount || '',
                    collects: interact.collectedCount || '',
                    comments: interact.commentCount || '',
                    shares: interact.shareCount || '',
                    type: note.type || '',
                    image_count: images.length,
                    images: images,
                    tag_list: tags,
                    publish_time: note.time || '',
                    ip_location: note.ipLocation || '',
                    note_id: note.noteId || noteId,
                };
            }
        }
    } catch(e) {}

    // DOM 兜底
    const titleEl = document.querySelector('.title, #detail-title, .note-title, [class*="note-title"], [class*="detail-title"], #detail-desc');
    const descEl = document.querySelector('#detail-desc, .note-scroller, [class*="note-scroller"], .note-text, [class*="note-text"]');
    const authorEl = document.querySelector('.author, .name, .username, .note-author, [class*="author"], [class*="note-author"]');
    const likeEl = document.querySelector('.like, .engage-bar .like, [class*="like"], [class*="engage"]');
    const collectEl = document.querySelector('.collect, .engage-bar .collect, [class*="collect"]');
    const commentEl = document.querySelector('.comment, .engage-bar .comment, [class*="comment"]');
    return {
        title: titleEl?.textContent?.trim() ?? null,
        desc: descEl?.textContent?.trim() ?? null,
        full_text: descEl?.textContent?.trim() ?? null,
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

                            # 提取 xsec_token（每个帖子唯一的安全令牌，访问详情必需）
                            xsec_token = (
                                note_card.get("xsec_token", "")
                                or item.get("xsec_token", "")
                            )
                            # 从分享链接 URL 中兜底提取
                            if not xsec_token:
                                share_link = (note_card.get("share_info", {}) or {}).get("link", "")
                                if "xsec_token=" in share_link:
                                    _m = re.search(r'xsec_token=([^&]+)', share_link)
                                    xsec_token = _m.group(1) if _m else ""

                            user = note_card.get("user", {}) or {}
                            interact = note_card.get("interact_info", {}) or {}
                            cover = note_card.get("cover", {}) or {}
                            image_list = note_card.get("image_list", []) or []

                            # 构造带 xsec_token 的详情 URL
                            detail_url = f"https://www.xiaohongshu.com/explore/{note_id}"
                            if xsec_token:
                                detail_url += f"?xsec_token={xsec_token}&xsec_source=pc_search"

                            api_items.append({
                                "note_id": note_id,
                                "xsec_token": xsec_token,
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
                                "url": detail_url,
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


async def xiaohongshu_note_detail(note_id: str, xsec_token: str = "") -> str:
    """获取小红书笔记详情 — CDP 浏览器拦截详情 API + DOM 兜底。需登入。回传 JSON 字串。

    Args:
        note_id: 笔记ID（如 6938f1a5000000001e03d4e3）
        xsec_token: 安全令牌（从搜索结果中获取，每个帖子唯一）
    """
    logger.info(f"小红书详情: note_id={note_id} xsec_token={xsec_token[:20] if xsec_token else '无'}...")
    try:
        page = await browser.new_page()
        try:
            detail_data: dict = {}

            async def on_response(resp):
                """拦截笔记详情 API，提取完整正文/图片/标签等。"""
                if ("/api/sns/web/v1/feed" in resp.url or "note_id" in resp.url) and resp.status == 200:
                    try:
                        body = await resp.json()
                        items = body.get("data", {}).get("items", []) or []
                        if not items:
                            # 有些接口返回单个 note
                            note_data = body.get("data", {}).get("note", {}) or body.get("data", {})
                            if note_data and note_data.get("note_id"):
                                items = [{"note_card": note_data}]
                        for item in items:
                            nc = item.get("note_card", item)
                            if str(nc.get("note_id", "")) != note_id:
                                continue
                            user = nc.get("user", {}) or {}
                            interact = nc.get("interact_info", {}) or {}
                            cover = nc.get("cover", {}) or {}
                            image_list = nc.get("image_list", []) or []
                            detail_data.update({
                                "title": nc.get("display_title", "") or nc.get("title", ""),
                                "desc": nc.get("desc", ""),
                                "full_text": nc.get("desc", ""),
                                "author": user.get("nickname", ""),
                                "author_id": user.get("user_id", ""),
                                "author_avatar": user.get("avatar", ""),
                                "likes": interact.get("liked_count", ""),
                                "collects": interact.get("collected_count", ""),
                                "comments": interact.get("comment_count", ""),
                                "shares": interact.get("share_count", ""),
                                "type": nc.get("type", ""),
                                "cover_url": cover.get("url_default", "") or cover.get("url", ""),
                                "image_count": len(image_list),
                                "images": [img.get("url_default", img.get("url", "")) for img in image_list],
                                "tag_list": [t.get("name", "") for t in (nc.get("tag_list", []) or []) if t.get("name")],
                                "publish_time": nc.get("time", ""),
                                "ip_location": nc.get("ip_location", ""),
                            })
                    except Exception:
                        pass

            page.on("response", lambda resp: asyncio.ensure_future(on_response(resp)))

            url = f"https://www.xiaohongshu.com/explore/{note_id}"
            if xsec_token:
                url += f"?xsec_token={xsec_token}&xsec_source=pc_search"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)

            # 等 API 响应返回
            await page.wait_for_timeout(2000)

            # DOM 兜底: API拦截失败时用CSS选择器
            if not detail_data:
                dom = await page.evaluate(_DETAIL_JS)
                if dom and isinstance(dom, dict):
                    detail_data = dom
                    logger.info("小红书详情: API 拦截为空，使用 DOM 兜底")

            title = detail_data.get("title", "N/A")
            logger.info(f"小红书详情完成: {title}")
            return json.dumps(detail_data, ensure_ascii=False)
        finally:
            await page.close()
    except Exception as e:
        logger.warning(f"小红书详情异常: {e}")
        return json.dumps({}, ensure_ascii=False)


async def xiaohongshu_comment(note_id: str, count: int = 50, xsec_token: str = "") -> str:
    """爬取小红书笔记评论 — CDP 浏览器拦截评论 API + DOM 兜底。需登入。回传 JSON 字串。

    Args:
        note_id: 笔记ID
        count: 评论数量
        xsec_token: 安全令牌（从搜索结果中获取）
    """
    logger.info(f"小红书评论: note_id={note_id} count={count} xsec_token={xsec_token[:20] if xsec_token else '无'}...")
    try:
        page = await browser.new_page()
        try:
            comments: list[dict] = []
            seen_cids: set[str] = set()

            async def on_response(resp):
                """拦截评论 API 响应，提取结构化字段。"""
                if "/api/sns/web/v2/comment" in resp.url and resp.status == 200:
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
            if xsec_token:
                url += f"?xsec_token={xsec_token}&xsec_source=pc_search"
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
    """爬取小红书推荐 feed（近似热榜）— CDP 浏览器拦截 API + DOM 兜底。需登入。回传 JSON 字串。"""
    logger.info("小红书热榜: 开始爬取")
    try:
        page = await browser.new_page()
        try:
            hot_items: list[dict] = []
            seen_ids: set[str] = set()

            async def on_response(resp):
                """拦截首页推荐 feed API。"""
                if ("/api/sns/web/v1/homefeed" in resp.url or "/api/sns/web/v1/feed" in resp.url) and resp.status == 200:
                    try:
                        body = await resp.json()
                        items = body.get("data", {}).get("items", []) or []
                        for item in items:
                            note_card = item.get("note_card") or item
                            note_id = str(item.get("id", "") or note_card.get("note_id", ""))
                            if not note_id or note_id in seen_ids:
                                continue
                            seen_ids.add(note_id)
                            xsec_token = (
                                note_card.get("xsec_token", "")
                                or item.get("xsec_token", "")
                            )
                            if not xsec_token:
                                share_link = (note_card.get("share_info", {}) or {}).get("link", "")
                                if "xsec_token=" in share_link:
                                    m = re.search(r'xsec_token=([^&]+)', share_link)
                                    xsec_token = m.group(1) if m else ""
                            user = note_card.get("user", {}) or {}
                            interact = note_card.get("interact_info", {}) or {}
                            cover = note_card.get("cover", {}) or {}
                            detail_url = f"https://www.xiaohongshu.com/explore/{note_id}"
                            if xsec_token:
                                detail_url += f"?xsec_token={xsec_token}&xsec_source=pc_feed"
                            hot_items.append({
                                "note_id": note_id,
                                "xsec_token": xsec_token,
                                "title": note_card.get("display_title", ""),
                                "author": user.get("nickname", ""),
                                "author_id": user.get("user_id", ""),
                                "likes": interact.get("liked_count", ""),
                                "cover_url": cover.get("url_default", "") or cover.get("url", ""),
                                "url": detail_url,
                            })
                    except Exception:
                        pass

            page.on("response", lambda resp: asyncio.ensure_future(on_response(resp)))

            await page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)

            # 滚动触发更多加载
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)

            await page.wait_for_timeout(2000)

            # DOM 兜底
            if not hot_items:
                dom_result = await page.evaluate(r"""() => {
    const items = document.querySelectorAll('.note-item, [class*="note-item"], [class*="feed"] [class*="item"]');
    const seen = new Set();
    const parseHref = (href) => {
        const m = href?.match(/\/(explore)\/([a-zA-Z0-9]+)/);
        const note_id = m ? m[2] : '';
        const xm = href?.match(/xsec_token=([^&]+)/);
        return {note_id, xsec_token: xm ? xm[1] : ''};
    };
    return Array.from(items).filter(el => {
        const t = el.textContent.trim();
        if (!t || t.length < 5 || seen.has(t)) return false;
        seen.add(t);
        return true;
    }).slice(0, 30).map(el => {
        const href = el.querySelector('a')?.getAttribute('href') || '';
        const {note_id, xsec_token} = parseHref(href);
        const coverEl = el.querySelector('img');
        const detail_url = note_id ? ('https://www.xiaohongshu.com/explore/' + note_id + (xsec_token ? '?xsec_token=' + xsec_token + '&xsec_source=pc_feed' : '')) : href;
        return {
            note_id, xsec_token,
            title: el.querySelector('.title, [class*="title"]')?.textContent?.trim() || '',
            likes: el.querySelector('.like, [class*="like"], [class*="count"]')?.textContent?.trim() || '',
            cover_url: coverEl?.getAttribute('src') || coverEl?.getAttribute('data-src') || '',
            url: detail_url,
        };
    });
}""")
                if dom_result:
                    hot_items = dom_result
                    logger.info("小红书热榜: API 拦截为空，使用 DOM 兜底")

            logger.info(f"小红书热榜完成: {len(hot_items)} 条")
            return json.dumps(hot_items, ensure_ascii=False)
        finally:
            await page.close()
    except Exception as e:
        logger.warning(f"小红书热榜异常: {e}")
        return json.dumps([], ensure_ascii=False)


async def xiaohongshu_user(user_id: str) -> str:
    """爬取小红书用户主页笔记列表 — CDP 浏览器。需登入。回传 JSON 字串。"""
    logger.info(f"小红书用户: user_id={user_id}")
    try:
        page = await browser.new_page()
        try:
            user_items: list[dict] = []
            seen_ids: set[str] = set()

            async def on_response(resp):
                """拦截用户主页笔记列表 API。"""
                if ("/api/sns/web/v1/user_posted" in resp.url or "user/notes" in resp.url) and resp.status == 200:
                    try:
                        body = await resp.json()
                        notes = body.get("data", {}).get("notes", []) or []
                        for note in notes:
                            note_id = str(note.get("note_id", ""))
                            if not note_id or note_id in seen_ids:
                                continue
                            seen_ids.add(note_id)
                            xsec_token = note.get("xsec_token", "")
                            if not xsec_token:
                                share_link = (note.get("share_info", {}) or {}).get("link", "")
                                if "xsec_token=" in share_link:
                                    m = re.search(r'xsec_token=([^&]+)', share_link)
                                    xsec_token = m.group(1) if m else ""
                            interact = note.get("interact_info", {}) or {}
                            cover = note.get("cover", {}) or {}
                            detail_url = f"https://www.xiaohongshu.com/explore/{note_id}"
                            if xsec_token:
                                detail_url += f"?xsec_token={xsec_token}&xsec_source=pc_user"
                            user_items.append({
                                "note_id": note_id,
                                "xsec_token": xsec_token,
                                "title": note.get("display_title", ""),
                                "likes": interact.get("liked_count", ""),
                                "collects": interact.get("collected_count", ""),
                                "comments": interact.get("comment_count", ""),
                                "cover_url": cover.get("url_default", "") or cover.get("url", ""),
                                "url": detail_url,
                            })
                    except Exception:
                        pass

            page.on("response", lambda resp: asyncio.ensure_future(on_response(resp)))

            await page.goto(f"https://www.xiaohongshu.com/user/profile/{user_id}", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)

            # 滚动加载更多
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)

            await page.wait_for_timeout(2000)

            # DOM 兜底
            if not user_items:
                dom_result = await page.evaluate(r"""() => {
    const items = document.querySelectorAll('.note-item, [class*="note-item"]');
    const seen = new Set();
    const parseHref = (href) => {
        const m = href?.match(/\/(explore)\/([a-zA-Z0-9]+)/);
        const note_id = m ? m[2] : '';
        const xm = href?.match(/xsec_token=([^&]+)/);
        return {note_id, xsec_token: xm ? xm[1] : ''};
    };
    return Array.from(items).filter(el => {
        const t = el.textContent.trim();
        if (!t || t.length < 3 || seen.has(t)) return false;
        seen.add(t);
        return true;
    }).slice(0, 30).map(el => {
        const href = el.querySelector('a')?.getAttribute('href') || '';
        const {note_id, xsec_token} = parseHref(href);
        const coverEl = el.querySelector('img');
        const detail_url = note_id ? ('https://www.xiaohongshu.com/explore/' + note_id + (xsec_token ? '?xsec_token=' + xsec_token + '&xsec_source=pc_user' : '')) : href;
        return {
            note_id, xsec_token,
            title: el.querySelector('.title, [class*="title"]')?.textContent?.trim() || '',
            likes: el.querySelector('.like, [class*="like"], [class*="count"]')?.textContent?.trim() || '',
            cover_url: coverEl?.getAttribute('src') || coverEl?.getAttribute('data-src') || '',
            url: detail_url,
        };
    });
}""")
                if dom_result:
                    user_items = dom_result
                    logger.info("小红书用户: API 拦截为空，使用 DOM 兜底")

            logger.info(f"小红书用户完成: {len(user_items)} 条")
            return json.dumps(user_items, ensure_ascii=False)
        finally:
            await page.close()
    except Exception as e:
        logger.warning(f"小红书用户异常: {e}")
        return json.dumps([], ensure_ascii=False)


class XiaohongshuAdapter(JsonAdapterMixin, PlatformAdapter):
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
            data = self._unwrap(await xiaohongshu_search(keyword, count=limit or 40), limit)
            if data:
                return data
        except Exception as e:
            logger.warning(f"[Xiaohongshu] API search failed: {e}, trying adaptive fallback")
        return await self._adaptive_search(keyword, limit)

    async def _adaptive_search(self, keyword: str, limit: Optional[int] = None) -> list[dict]:
        """HTTP 搜索失败时的浏览器兜底搜索。"""
        try:
            if not browser.is_running:
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
        return self._unwrap(await xiaohongshu_hot(), limit)

    async def detail(self, item_id: str, xsec_token: str = "", **kwargs) -> dict:
        return self._unwrap_dict(await xiaohongshu_note_detail(item_id, xsec_token=xsec_token))

    async def comment(self, item_id: str, limit: Optional[int] = None, xsec_token: str = "", **kwargs) -> list[dict]:
        return self._unwrap(await xiaohongshu_comment(item_id, count=limit or 50, xsec_token=xsec_token), limit)

    async def user(self, user_id: str, limit: Optional[int] = None) -> list[dict]:
        return self._unwrap(await xiaohongshu_user(user_id), limit)
