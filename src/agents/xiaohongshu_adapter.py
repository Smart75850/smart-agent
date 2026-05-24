import json
from typing import Optional

from base.platform_base import PlatformAdapter
from src.utils.browser_service import browser
from src.utils.logger import logger

# 需登入：小紅薯搜索頁面有 login overlay，未登入無法提取結果。
# Phase 1 加載 cookie 後可正常工作。
_SEARCH_JS = """\
() => {
    const items = document.querySelectorAll('.note-item, .feeds-page .note-item, [class*="note-item"]');
    return Array.from(items).map(item => {
        const titleEl = item.querySelector('.title') || item.querySelector('[class*="title"]');
        const authorEl = item.querySelector('.author, .name, .username, [class*="author"], [class*="name"]');
        const likeEl = item.querySelector('.like, .engage-bar, [class*="like"], [class*="engage"]');
        const linkEl = item.querySelector('a[href*="explore"], a[href*="note"]');
        return {
            title: titleEl?.textContent?.trim() ?? null,
            author: authorEl?.textContent?.trim() ?? null,
            likes: likeEl?.textContent?.trim() ?? null,
            note_id: linkEl?.getAttribute('href')?.match(/explore\\/([^?&/]+)/)?.[1] ?? null,
            link: linkEl?.getAttribute('href') ?? null,
        };
    });
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


async def xiaohongshu_search(keyword: str) -> str:
    """搜索小紅薯筆記，需登入先有完整內容。回傳 JSON 字串。"""
    logger.info(f"小紅薯搜索: keyword={keyword}")
    url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}&source=web_search_result_notes"
    result = await browser.evaluate(url, _SEARCH_JS)
    logger.info(f"小紅薯搜索完成: {len(result)} 條結果")
    return json.dumps(result, ensure_ascii=False)


async def xiaohongshu_note_detail(note_id: str) -> str:
    """獲取小紅薯筆記詳情，需登入先有完整內容。回傳 JSON 字串。"""
    logger.info(f"小紅薯詳情: note_id={note_id}")
    url = f"https://www.xiaohongshu.com/explore/{note_id}"
    result = await browser.evaluate(url, _DETAIL_JS)
    title = result.get("title", "N/A") if isinstance(result, dict) else "N/A"
    logger.info(f"小紅薯詳情完成: {title}")
    return json.dumps(result, ensure_ascii=False)


async def xiaohongshu_comment(note_id: str) -> str:
    """爬取小紅薯筆記評論，需登入先有完整內容。回傳 JSON 字串。"""
    logger.info(f"小紅薯評論: note_id={note_id}")
    page = await browser.new_page()
    try:
        await page.goto(f"https://www.xiaohongshu.com/explore/{note_id}", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        result = await page.evaluate("""() => {
    const items = document.querySelectorAll('[class*="comment-item"], [class*="CommentItem"], .comment-item');
    const seen = new Set();
    return Array.from(items).filter(item => {
        const t = item.textContent.trim();
        return t && t.length >= 2 && !seen.has(t) && (seen.add(t), true);
    }).map(item => ({
        content: item.querySelector('[class*="content"], [class*="text"], .content, .text')?.textContent?.trim() || item.textContent.trim().slice(0, 200),
        // 🆕 二級評論
        replies: Array.from(item.querySelectorAll('[class*="reply-item"], [class*="ReplyItem"], .reply-item')).map(r => ({
            content: r.querySelector('[class*="text"], [class*="content"], .text, .content')?.textContent?.trim() || r.textContent.trim().slice(0, 200),
        })),
    }));
}""")
        logger.info(f"小紅薯評論完成: {len(result)} 條")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


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

    async def search(self, keyword: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await xiaohongshu_search(keyword))
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
