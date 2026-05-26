import json
from typing import Optional

from base.platform_base import PlatformAdapter
from src.utils.browser_service import browser
from src.utils.logger import logger

_HOT_JS = """\
() => {
    const items = document.querySelectorAll('.threadlist_title, .j_thread_list, [class*="thread"]');
    if (items.length === 0) {
        const cards = document.querySelectorAll('[class*="card"], [class*="item"], li');
        return Array.from(cards).slice(0, 30).map((el, i) => ({
            rank: String(i + 1),
            title: el.querySelector('a[class*="title"], a[href*="/p/"], a')?.textContent?.trim() || '',
            author: el.querySelector('[class*="author"], [class*="user"], [class*="name"]')?.textContent?.trim() || '',
            replies: el.querySelector('[class*="reply"], [class*="count"], [class*="num"]')?.textContent?.trim() || '',
            link: el.querySelector('a[href*="/p/"]')?.getAttribute('href') || '',
        })).filter(x => x.title.length > 2);
    }
    return Array.from(items).slice(0, 30).map((el, i) => ({
        rank: String(i + 1),
        title: el.querySelector('.threadlist_title a, a[class*="title"], a[href*="/p/"]')?.textContent?.trim() || el.querySelector('a')?.textContent?.trim() || '',
        author: el.querySelector('.threadlist_author, .frs-author-name, [class*="author"]')?.textContent?.trim() || '',
        replies: el.querySelector('.threadlist_rep_num, [class*="reply"]')?.textContent?.trim() || '',
        link: el.querySelector('a[href*="/p/"]')?.getAttribute('href') || '',
    })).filter(x => x.title.length > 2);
}"""

_SEARCH_JS = """\
() => {
    const items = document.querySelectorAll('.s_post, .search_post, [class*="search"] [class*="post"], .p_post');
    if (items.length === 0) {
        const all = document.querySelectorAll('[class*="item"], [class*="list"] li, .thread_list li');
        return Array.from(all).slice(0, 30).map(el => ({
            title: el.querySelector('a[href*="/p/"], a[class*="title"], a')?.textContent?.trim() || '',
            author: el.querySelector('[class*="author"], [class*="user"], [class*="name"]')?.textContent?.trim() || '',
            excerpt: el.querySelector('[class*="content"], [class*="abstract"], p')?.textContent?.trim()?.slice(0, 200) || '',
            replies: el.querySelector('[class*="reply"], [class*="count"]')?.textContent?.trim() || '',
            link: el.querySelector('a[href*="/p/"]')?.getAttribute('href') || '',
        })).filter(x => x.title.length > 3);
    }
    return Array.from(items).slice(0, 30).map(el => ({
        title: el.querySelector('a[href*="/p/"], a[class*="title"], .p_title a')?.textContent?.trim() || '',
        author: el.querySelector('.p_author, [class*="author"], [class*="user"]')?.textContent?.trim() || '',
        excerpt: el.querySelector('.p_content, [class*="abstract"], .p_abstract')?.textContent?.trim()?.slice(0, 200) || '',
        replies: el.querySelector('.p_reply, [class*="reply"], [class*="count"]')?.textContent?.trim() || '',
        link: el.querySelector('a[href*="/p/"]')?.getAttribute('href') || '',
    }));
}"""


async def tieba_hot() -> str:
    logger.info("贴吧热榜: 开始爬取")
    page = await browser.new_page()
    try:
        await page.goto("https://tieba.baidu.com/hottopic/browse/topicList", wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)
        result = await page.evaluate(_HOT_JS)
        if not result:
            await page.goto("https://tieba.baidu.com/", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            result = await page.evaluate(_HOT_JS)
        logger.info(f"贴吧热榜完成: {len(result)} 条结果")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


async def tieba_search(keyword: str) -> str:
    logger.info(f"贴吧搜索: keyword={keyword}")
    page = await browser.new_page()
    try:
        await page.goto(
            f"https://tieba.baidu.com/f/search/res?qw={keyword}",
            wait_until="domcontentloaded",
        )
        await page.wait_for_timeout(5000)
        result = await page.evaluate(_SEARCH_JS)
        logger.info(f"贴吧搜索完成: {len(result)} 条结果")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


async def tieba_detail(tid: str) -> str:
    logger.info(f"贴吧详情: tid={tid}")
    page = await browser.new_page()
    try:
        if not tid.startswith("https://"):
            tid = f"https://tieba.baidu.com/p/{tid}"
        await page.goto(tid, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        result = await page.evaluate("""() => {
    const title = document.querySelector('.core_title_txt, [class*="title"]')?.textContent?.trim() || '';
    const content = document.querySelector('.d_post_content, [class*="content"]')?.textContent?.trim()?.slice(0, 500) || '';
    const author = document.querySelector('.d_author, [class*="author"]')?.textContent?.trim() || '';
    return {title, content, author};
}""")
        logger.info(f"贴吧详情完成: {result.get('title', 'N/A')[:30] if isinstance(result, dict) else 'N/A'}")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


async def tieba_comment(tid: str) -> str:
    logger.info(f"贴吧评论: tid={tid}")
    page = await browser.new_page()
    try:
        if not tid.startswith("https://"):
            tid = f"https://tieba.baidu.com/p/{tid}"
        await page.goto(tid, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        result = await page.evaluate("""() => {
    const items = document.querySelectorAll('.lzl_cnt, .j_lzl_container [class*="item"], .lzl_single_post');
    if (items.length === 0) {
        const replies = document.querySelectorAll('.d_post_content, [class*="content"]');
        return Array.from(replies).slice(1, 31).map(r => {
            const authorEl = r.closest('[class*="post"], [class*="item"]')?.querySelector('[class*="author"], [class*="name"]');
            return {
                user: authorEl?.textContent?.trim() || '',
                content: r.textContent?.trim()?.slice(0, 300) || '',
                likes: '',
            };
        });
    }
    return Array.from(items).slice(0, 30).map(item => ({
        user: item.querySelector('[class*="user"], [class*="name"], [class*="author"]')?.textContent?.trim() || '',
        content: item.querySelector('[class*="content"], [class*="text"]')?.textContent?.trim() || item.textContent.trim().slice(0, 200),
        likes: item.querySelector('[class*="like"], [class*="agree"]')?.textContent?.trim() || '',
    }));
}""")
        logger.info(f"贴吧评论完成: {len(result)} 条")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


async def tieba_user(user_id: str) -> str:
    logger.info(f"贴吧用户: user_id={user_id}")
    page = await browser.new_page()
    try:
        await page.goto(f"https://tieba.baidu.com/home/main?un={user_id}", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        result = await page.evaluate("""() => {
    const items = document.querySelectorAll('.thread_item, [class*="thread"] [class*="item"], [class*="list"] li');
    return Array.from(items).slice(0, 20).map(el => ({
        title: el.querySelector('a[href*="/p/"], a[class*="title"], a')?.textContent?.trim() || '',
        excerpt: el.querySelector('[class*="content"], [class*="abstract"]')?.textContent?.trim()?.slice(0, 200) || '',
        link: el.querySelector('a[href*="/p/"]')?.getAttribute('href') || '',
    }));
}""")
        logger.info(f"贴吧用户完成: {len(result)} 条")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


class TiebaAdapter(PlatformAdapter):
    @property
    def name(self) -> str:
        return "tieba"

    @property
    def need_login(self) -> bool:
        return False

    async def search(self, keyword: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await tieba_search(keyword))
        return data[:limit] if limit else data

    async def hot(self, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await tieba_hot())
        return data[:limit] if limit else data

    async def detail(self, item_id: str, **kwargs) -> dict:
        return json.loads(await tieba_detail(item_id))

    async def comment(self, item_id: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await tieba_comment(item_id))
        return data[:limit] if limit else data

    async def user(self, user_id: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await tieba_user(user_id))
        return data[:limit] if limit else data
