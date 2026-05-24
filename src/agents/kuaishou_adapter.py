import json
from typing import Optional

from base.platform_base import PlatformAdapter
from src.utils.browser_service import browser
from src.utils.logger import logger

_SEARCH_JS = """\
() => {
    const items = document.querySelectorAll(
        'a[href*="/photo"], [class*="video-card"], [class*="search-result"] a, [class*="card"] a[href*="photo"]'
    );
    const seen = new Set();
    const results = [];
    items.forEach(el => {
        const href = el.getAttribute('href');
        if (!href || seen.has(href)) return;
        seen.add(href);
        const titleEl = el.querySelector('[class*="title"], [class*="desc"], [class*="subject"]');
        const authorEl = el.querySelector('[class*="name"], [class*="author"], [class*="user"]');
        const playEl = el.querySelector('[class*="play"], [class*="watch"], [class*="count"]');
        results.push({
            title: titleEl?.textContent?.trim() ?? null,
            author: authorEl?.textContent?.trim() ?? null,
            plays: playEl?.textContent?.trim() ?? null,
            link: href ?? null,
        });
    });
    if (results.length === 0) {
        const photoLinks = document.querySelectorAll('a[href*="/photo"]');
        photoLinks.forEach(a => {
            const href = a.getAttribute('href');
            if (!href || seen.has(href)) return;
            seen.add(href);
            results.push({
                title: a.textContent?.trim()?.slice(0, 100) ?? null,
                author: null,
                plays: null,
                link: href,
            });
        });
    }
    return results;
}"""

_HOT_JS = """\
() => {
    const results = [];
    const seen = new Set();
    const plainEls = document.querySelectorAll('.plain');
    plainEls.forEach(el => {
        const title = el?.textContent?.trim();
        if (!title || title.length < 3 || seen.has(title)) return;
        seen.add(title);
        const authorEl = document.querySelector('a.name');
        results.push({
            title: title,
            heat: authorEl?.textContent?.trim() ?? null,
            link: null,
        });
    });
    return results;
}"""


async def kuaishou_search(keyword: str) -> str:
    """搜索快手視頻，需登入先有結果。回傳 JSON 字串。"""
    logger.info(f"快手搜索: keyword={keyword}")
    url = f"https://www.kuaishou.com/search/video?searchKey={keyword}"
    result = await browser.evaluate(url, _SEARCH_JS)
    logger.info(f"快手搜索完成: {len(result)} 條結果")
    return json.dumps(result, ensure_ascii=False)


async def kuaishou_hot() -> str:
    """爬取快手熱榜（/discover/hot → /new-reco），回傳 JSON 字串。"""
    logger.info("快手熱榜: 開始爬取")
    page = await browser.new_page()
    try:
        await page.goto("https://www.kuaishou.com/new-reco", wait_until="domcontentloaded")
        await page.wait_for_timeout(8000)
        result = await page.evaluate(_HOT_JS)
        logger.info(f"快手熱榜完成: {len(result)} 條結果")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


async def kuaishou_detail(photo_id: str) -> str:
    """爬取快手視頻詳情，需登入先有完整內容。回傳 JSON 字串。"""
    logger.info(f"快手詳情: photo_id={photo_id}")
    page = await browser.new_page()
    try:
        await page.goto(f"https://www.kuaishou.com/photo/{photo_id}", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        result = await page.evaluate("""() => {
    const titleEl = document.querySelector('[class*="title"], [class*="desc"], h1');
    const authorEl = document.querySelector('[class*="name"], [class*="author"], [class*="user"]');
    const playEl = document.querySelector('[class*="play"], [class*="watch"], [class*="count"]');
    const likeEl = document.querySelector('[class*="like"], [class*="Like"], [class*="digg"]');
    return {
        title: titleEl?.textContent?.trim() || '',
        author: authorEl?.textContent?.trim() || '',
        plays: playEl?.textContent?.trim() || '',
        likes: likeEl?.textContent?.trim() || '',
    };
}""")
        logger.info("快手詳情完成")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


async def kuaishou_comment(photo_id: str) -> str:
    """爬取快手視頻評論，需登入先有完整內容。回傳 JSON 字串。"""
    logger.info(f"快手評論: photo_id={photo_id}")
    page = await browser.new_page()
    try:
        await page.goto(f"https://www.kuaishou.com/photo/{photo_id}", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        result = await page.evaluate("""() => {
    // 一級評論 container
    const containers = document.querySelectorAll('[class*="commentItem"], [class*="CommentItem"], [class*="comment-item"], [class*="parent"]');
    if (containers.length > 0) {
        const seen = new Set();
        return Array.from(containers).filter(c => {
            const t = c.textContent.trim();
            return t && t.length >= 5 && !seen.has(t) && (seen.add(t), true);
        }).map(c => ({
            content: c.querySelector('[class*="text"], [class*="content"], p, span')?.textContent?.trim() || c.textContent.trim().slice(0, 200),
            // 🆕 二級評論
            replies: Array.from(c.querySelectorAll('[class*="reply"], [class*="Reply"], [class*="sub"]')).map(r => ({
                content: r.querySelector('[class*="text"], [class*="content"], p, span')?.textContent?.trim() || r.textContent.trim().slice(0, 200),
            })),
        }));
    }
    // fallback: flat 模式
    const items = document.querySelectorAll('[class*="comment"] [class*="text"], [class*="comment"] p, [class*="Comment"] p, [class*="reply"] [class*="content"]');
    const seen = new Set();
    return Array.from(items).filter(el => {
        const t = el.textContent.trim();
        return t && t.length >= 2 && !seen.has(t) && (seen.add(t), true);
    }).map(el => ({ content: el.textContent.trim(), replies: [] }));
}""")
        logger.info(f"快手評論完成: {len(result)} 條")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


async def kuaishou_user(user_id: str) -> str:
    """爬取快手用戶主頁視頻列表，需登入先有完整內容。回傳 JSON 字串。"""
    logger.info(f"快手用戶: user_id={user_id}")
    page = await browser.new_page()
    try:
        await page.goto(f"https://www.kuaishou.com/profile/{user_id}", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        result = await page.evaluate("""() => {
    const items = document.querySelectorAll('a[href*="/photo"], [class*="video"], [class*="card"]');
    const seen = new Set();
    const results = [];
    items.forEach(el => {
        const href = el.getAttribute('href');
        if (!href || seen.has(href)) return;
        seen.add(href);
        const titleEl = el.querySelector('[class*="title"], [class*="desc"]');
        const playEl = el.querySelector('[class*="play"], [class*="watch"]');
        results.push({
            title: titleEl?.textContent?.trim() ?? null,
            plays: playEl?.textContent?.trim() ?? null,
            link: href ?? null,
        });
    });
    return results;
}""")
        logger.info(f"快手用戶完成: {len(result)} 條")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


class KuaishouAdapter(PlatformAdapter):
    @property
    def name(self) -> str:
        return "kuaishou"

    @property
    def need_login(self) -> bool:
        return True

    async def search(self, keyword: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await kuaishou_search(keyword))
        return data[:limit] if limit else data

    async def hot(self, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await kuaishou_hot())
        return data[:limit] if limit else data

    async def detail(self, item_id: str, **kwargs) -> dict:
        return json.loads(await kuaishou_detail(item_id))

    async def comment(self, item_id: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await kuaishou_comment(item_id))
        return data[:limit] if limit else data

    async def user(self, user_id: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await kuaishou_user(user_id))
        return data[:limit] if limit else data
