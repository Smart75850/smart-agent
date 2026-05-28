import asyncio
import json
import os
from pathlib import Path
from typing import Optional

from base.platform_base import PlatformAdapter
from src.utils.browser_service import browser
from src.utils.logger import logger

_COOKIE_FILE = Path(__file__).parent.parent.parent / "output" / "xiaohongshu_cookies.json"
_PERSIST_DIR = Path(os.environ.get("TEMP", r"C:\tmp")) / "pw_xhs_live"
_CAMOUFOX_PERSIST_DIR = Path(os.environ.get("TEMP", r"C:\tmp")) / "cf_xhs_live"


async def _setup_xhs_context():
    """根据 BROWSER_ENGINE 返回 (page, cleanup_coro)。

    Camoufox 走 AsyncCamoufox persistent profile；
    Chromium 走 launch_persistent_context。
    自动注入 CookieBridge 保存的 cookies。
    """
    engine = os.environ.get("BROWSER_ENGINE", "")
    from config.settings import settings

    if engine == "camoufox":
        from playwright.async_api import async_playwright
        from camoufox.async_api import AsyncNewBrowser
        pw = await async_playwright().start()
        context = await AsyncNewBrowser(
            pw,
            persistent_context=True,
            headless=False,
            humanize=True,
            locale="zh-CN",
            os=settings.CAMOUFOX_OS or "windows",
            block_webrtc=True,
            user_data_dir=str(_CAMOUFOX_PERSIST_DIR),
            screen={"width": 1920, "height": 1080},
        )
        page = context.pages[0] if context.pages else await context.new_page()

        async def cleanup():
            await context.close()
            await pw.stop()

        return page, cleanup

    else:
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(_PERSIST_DIR),
            headless=False,
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            args=["--no-sandbox"],
        )

        # 注入 CookieBridge cookies
        await _inject_cookies(context)

        page = context.pages[0] if context.pages else await context.new_page()

        async def cleanup():
            await context.close()
            await pw.stop()

        return page, cleanup


async def _inject_cookies(context):
    """从 CookieBridge JSON 文件注入 cookies 到上下文。"""
    cookie_dir = Path("browser_data")
    if not cookie_dir.exists():
        return
    for filepath in list(cookie_dir.glob("cookies_*.json")) + list(cookie_dir.glob("*_cookies.json")):
        try:
            cookies = json.loads(filepath.read_text(encoding="utf-8"))
            if cookies:
                await context.add_cookies(cookies)
                platform = filepath.stem.replace("_cookies", "")
                logger.info(f"XHS CookieBridge: {platform} 注入 {len(cookies)} 个 cookie")
        except Exception:
            pass

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
        const coverEl = el.querySelector('img') || el.querySelector('[class*="cover"] img') || el.querySelector('[class*="image"] img');
        const cover = coverEl ? (coverEl.getAttribute('src') || coverEl.getAttribute('data-src') || '') : '';
        if (title.length > 3) out.push({title: title, author: author, likes: likes, link: href, cover_url: cover});
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
    """搜索小紅薯筆記 — 纯 HTTP Session 优先，浏览器兜底。"""
    logger.info(f"小紅薯搜索: keyword={keyword} count={count}")

    # ── Path 1: 纯 HTTP Session（零浏览器）─────────────────
    try:
        from src.utils.session_manager import ensure_session
        if await ensure_session("xiaohongshu"):
            from src.utils.xhs_http import search_all
            items = await search_all(keyword, limit=count)
            if items:
                logger.info(f"[xhs-session] 纯HTTP直连成功: {len(items)} 条")
                return json.dumps(items, ensure_ascii=False)
    except Exception as exc:
        logger.warning(f"XHS Session HTTP 失败: {exc}，回退浏览器")

    # ── Path 2: CDP 浏览器（兜底）─────────────────────────

    page, cleanup = await _setup_xhs_context()

    try:
        search_url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}&source=web_search_result_notes"
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

        # 檢查登入牆
        body = await page.evaluate("() => document.body.textContent.substring(0, 500)")
        if "登录后查看" in body:
            logger.warning("小紅薯未登入，請先執行 login_search_xhs.py 掃碼登入")
            return json.dumps([], ensure_ascii=False)

        all_results = []
        seen = set()
        max_scrolls = max((count // 30) + 3, 5)

        for _ in range(max_scrolls):
            items = await page.evaluate(_SEARCH_JS)
            new_count = 0
            for item in items:
                key = item.get("link", "") or item.get("title", "")
                if key and key not in seen:
                    seen.add(key)
                    all_results.append(item)
                    new_count += 1

            if new_count == 0 and len(all_results) > 0:
                break

            if len(all_results) >= count:
                break

            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2500)

        result = all_results[:count]
        logger.info(f"小紅薯搜索完成: {len(result)} 條")
        return json.dumps(result, ensure_ascii=False)

    finally:
        await cleanup()


async def xiaohongshu_note_detail(note_id: str) -> str:
    """獲取小紅薯筆記詳情，需登入先有完整內容。回傳 JSON 字串。"""
    logger.info(f"小紅薯詳情: note_id={note_id}")
    url = f"https://www.xiaohongshu.com/explore/{note_id}"
    result = await browser.evaluate(url, _DETAIL_JS)
    title = result.get("title", "N/A") if isinstance(result, dict) else "N/A"
    logger.info(f"小紅薯詳情完成: {title}")
    return json.dumps(result, ensure_ascii=False)


async def xiaohongshu_comment(note_id: str) -> str:
    """爬取小紅薯筆記評論，使用 persistent context 以保持登入態。"""
    logger.info(f"小紅薯評論: note_id={note_id}")

    page, cleanup = await _setup_xhs_context()

    try:
        await page.goto(f"https://www.xiaohongshu.com/explore/{note_id}", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)
        # 滚动触发评论加载
        for _ in range(5):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1500)
        result = await page.evaluate("""() => {
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
    // 如果没找到足够评论，提取页面文本块兜底
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
        logger.info(f"小紅薯評論完成: {len(result)} 條")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await cleanup()


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
    @property
    def name(self) -> str:
        return "xiaohongshu"

    @property
    def need_login(self) -> bool:
        return True

    async def search(self, keyword: str, limit: Optional[int] = None,
                     sort_type: int = 0, publish_time: int = 0,
                     search_channel: str = "") -> list[dict]:
        data = json.loads(await xiaohongshu_search(keyword, count=limit or 40))
        return data[:limit] if limit else data

    async def hot(self, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await xiaohongshu_hot())
        return data[:limit] if limit else data

    async def detail(self, item_id: str, xsec_token: str = "", **kwargs) -> dict:
        return json.loads(await xiaohongshu_note_detail(item_id))

    async def comment(self, item_id: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await xiaohongshu_comment(item_id))
        return data[:limit] if limit else data

    async def user(self, user_id: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await xiaohongshu_user(user_id))
        return data[:limit] if limit else data
