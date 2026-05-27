import json
from typing import Optional

from base.platform_base import PlatformAdapter
from src.utils.browser_service import browser
from src.utils.logger import logger

_HOT_JS = """\
async () => {
    try {
        const resp = await fetch('https://weibo.com/ajax/side/hotSearch', {credentials: 'include'});
        const data = await resp.json();
        const items = (data.data && data.data.realtime) ? data.data.realtime : [];
        return items.map(item => ({
            rank: item.rank || '',
            title: item.word || item.note || '',
            heat: item.num || '',
            category: item.category || '',
            link: 'https://s.weibo.com/weibo?q=' + encodeURIComponent(item.word || item.note || ''),
        }));
    } catch {
        const items = document.querySelectorAll('.hot_list .data, .hot_ranklist [class*="item"], .UG_rank_item');
        return Array.from(items).map((el, i) => ({
            rank: String(i + 1),
            title: el.querySelector('.title, a, [class*="text"]')?.textContent?.trim() || '',
            heat: el.querySelector('.num, [class*="count"], [class*="hot"]')?.textContent?.trim() || '',
            link: el.querySelector('a')?.getAttribute('href') || '',
        }));
    }
}"""

_SEARCH_JS = """\
() => {
    const cards = document.querySelectorAll('.card-wrap, .m-wrap, [class*="card"], [class*="Card"]');
    if (cards.length === 0) {
        const all = document.querySelectorAll('.m-con-l .card, .m-main .card, [action-type="feed_list_item"]');
        return Array.from(all).slice(0, 30).map(el => ({
            title: el.querySelector('.txt, .content, [class*="text"]')?.textContent?.trim()?.slice(0, 200) || '',
            author: el.querySelector('.name, .nickname, [class*="nick"]')?.textContent?.trim() || '',
            plays: el.querySelector('[class*="view"], [class*="play"]')?.textContent?.trim() || '',
            likes: el.querySelector('[class*="like"], [class*="attitude"], [class*="star"]')?.textContent?.trim() || '',
            link: el.querySelector('a[href*="/weibo/"], a[href*="/detail/"], a[href*="weibo.com"]')?.getAttribute('href') || '',
        })).filter(x => x.title.length > 3);
    }
    const seen = new Set();
    return Array.from(cards).map(card => {
        const title = card.querySelector('.txt, .content, [class*="text"], p')?.textContent?.trim()?.slice(0, 200) || '';
        if (!title || title.length < 3 || seen.has(title)) return null;
        seen.add(title);
        return {
            title,
            author: card.querySelector('.name, .nickname, [class*="nick"], [class*="user"]')?.textContent?.trim() || '',
            plays: card.querySelector('[class*="view"], [class*="play"]')?.textContent?.trim() || '',
            likes: card.querySelector('[class*="like"], [class*="attitude"], [class*="star"], [class*="count"]')?.textContent?.trim() || '',
            link: card.querySelector('a')?.getAttribute('href') || '',
        };
    }).filter(Boolean);
}"""


async def weibo_hot() -> str:
    logger.info("微博热榜: 开始爬取")
    page = await browser.new_page()
    try:
        await page.goto("https://weibo.com/hot/search", wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)
        result = await page.evaluate(_HOT_JS)
        logger.info(f"微博热榜完成: {len(result)} 条结果")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


async def weibo_search(keyword: str) -> str:
    """搜索微博。Path 1: 纯 HTTP Session → Path 2: CDP Browser"""
    logger.info(f"微博搜索: keyword={keyword}")

    # Path 1: 纯 HTTP Session（零浏览器，毫秒级）
    try:
        from src.utils.session_manager import ensure_session
        if await ensure_session("weibo"):
            from src.utils.weibo_http import search_all
            items = await search_all(keyword, limit=20)
            if items:
                logger.info(f"[weibo-session] 纯HTTP直连成功: {len(items)} 条")
                return json.dumps(items, ensure_ascii=False)
    except Exception as exc:
        logger.warning(f"微博 Session HTTP 失败: {exc}，尝试 CDP 浏览器路径")

    # Path 2: CDP Browser
    page = await browser.new_page()
    try:
        await page.goto(
            f"https://s.weibo.com/weibo?q={keyword}",
            wait_until="domcontentloaded",
        )
        await page.wait_for_timeout(5000)
        result = await page.evaluate(_SEARCH_JS)
        logger.info(f"微博搜索完成: {len(result)} 条结果")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


async def weibo_detail(weibo_id: str) -> str:
    logger.info(f"微博详情: weibo_id={weibo_id}")
    page = await browser.new_page()
    try:
        await page.goto(f"https://weibo.com/{weibo_id}", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        result = await page.evaluate("""() => {
    const content = document.querySelector('.detail_wbtext, .WB_text, [class*="detail"] [class*="text"]');
    const author = document.querySelector('.username, .W_autocut, [class*="name"]');
    return {
        title: content?.textContent?.trim()?.slice(0, 300) || '',
        author: author?.textContent?.trim() || '',
        reposts: document.querySelector('[class*="repost"] [class*="count"], [action-type="feed_list_forward"] em')?.textContent?.trim() || '',
        comments: document.querySelector('[class*="comment"] [class*="count"], [action-type="feed_list_comment"] em')?.textContent?.trim() || '',
        likes: document.querySelector('[class*="like"] [class*="count"], [action-type="feed_list_like"] em')?.textContent?.trim() || '',
    };
}""")
        logger.info(f"微博详情完成: {result.get('title', 'N/A')[:30] if isinstance(result, dict) else 'N/A'}")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


async def weibo_comment(weibo_id: str) -> str:
    logger.info(f"微博评论: weibo_id={weibo_id}")
    page = await browser.new_page()
    try:
        await page.goto(f"https://weibo.com/{weibo_id}", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        result = await page.evaluate("""() => {
    const items = document.querySelectorAll('.comment_item, .CommentItem, [class*="comment"] [class*="item"]');
    return Array.from(items).slice(0, 30).map(item => ({
        user: item.querySelector('.username, .W_autocut, [class*="name"], [class*="nick"]')?.textContent?.trim() || '',
        content: item.querySelector('.comment_txt, .WB_text, [class*="text"]')?.textContent?.trim() || '',
        likes: item.querySelector('[class*="like"], [class*="attitude"]')?.textContent?.trim() || '',
    }));
}""")
        logger.info(f"微博评论完成: {len(result)} 条")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


async def weibo_user(user_id: str) -> str:
    logger.info(f"微博用户: user_id={user_id}")
    page = await browser.new_page()
    try:
        await page.goto(f"https://weibo.com/u/{user_id}", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        result = await page.evaluate("""() => {
    const items = document.querySelectorAll('.UG_list_a .list_des, [class*="feed"] [class*="item"], [action-type="feed_list_item"]');
    const seen = new Set();
    return Array.from(items).filter(el => {
        const t = el.textContent.trim();
        if (!t || t.length < 5 || seen.has(t)) return false;
        seen.add(t);
        return true;
    }).slice(0, 20).map(el => ({
        title: el.querySelector('.WB_text, .list_des .S_txt1, [class*="text"]')?.textContent?.trim()?.slice(0, 200) || '',
        likes: el.querySelector('[class*="like"], [class*="attitude"] [class*="count"]')?.textContent?.trim() || '',
        link: el.querySelector('a[href*="/weibo/"], a[href*="/detail/"]')?.getAttribute('href') || '',
    }));
}""")
        logger.info(f"微博用户完成: {len(result)} 条")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


class WeiboAdapter(PlatformAdapter):
    @property
    def name(self) -> str:
        return "weibo"

    @property
    def need_login(self) -> bool:
        return True

    async def search(self, keyword: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await weibo_search(keyword))
        return data[:limit] if limit else data

    async def hot(self, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await weibo_hot())
        return data[:limit] if limit else data

    async def detail(self, item_id: str, **kwargs) -> dict:
        return json.loads(await weibo_detail(item_id))

    async def comment(self, item_id: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await weibo_comment(item_id))
        return data[:limit] if limit else data

    async def user(self, user_id: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await weibo_user(user_id))
        return data[:limit] if limit else data
