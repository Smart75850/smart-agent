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
    // tieba 新版搜索页 (Vue SPA): .threadcardclass.thread-new*
    const cards = document.querySelectorAll('[class*="threadcard"][class*="thread-new"]');
    if (cards.length > 0) {
        return Array.from(cards).slice(0, 30).map(card => {
            const linkEl = card.querySelector('a[href*="/p/"]');
            return {
                title: card.querySelector('.title-wrap span')?.textContent?.trim() || card.querySelector('.title-wrap')?.textContent?.trim() || '',
                author: card.querySelector('.forum-attention')?.textContent?.trim() || card.querySelector('.user-forum-info span:last-child')?.textContent?.trim() || '',
                excerpt: card.querySelector('.abstract-wrap')?.textContent?.trim()?.slice(0, 200) || '',
                replies: card.querySelector('.comment-link-zone')?.textContent?.trim() || '',
                forum: card.querySelector('.forum-name-text')?.textContent?.trim() || '',
                link: linkEl?.getAttribute('href') || '',
            };
        }).filter(x => x.title.length > 2);
    }
    // 旧版 DOM fallback
    let items = document.querySelectorAll('.s_post, .search_post, .p_post, [class*="search"] [class*="result"], .thread_list li, .tl-item');
    if (items.length === 0) {
        const all = document.querySelectorAll('li[class], div[class*="item"], div[class*="card"], div[class*="post"]');
        return Array.from(all).slice(0, 30).map(el => ({
            title: el.querySelector('a[href*="/p/"], a[class*="title"], a')?.textContent?.trim() || '',
            author: el.querySelector('[class*="author"], [class*="user"], [class*="name"]')?.textContent?.trim() || '',
            excerpt: el.querySelector('[class*="content"], [class*="abstract"], [class*="desc"], p')?.textContent?.trim()?.slice(0, 200) || '',
            replies: el.querySelector('[class*="reply"], [class*="count"], [class*="num"]')?.textContent?.trim() || '',
            link: el.querySelector('a[href*="/p/"]')?.getAttribute('href') || el.querySelector('a')?.getAttribute('href') || '',
        })).filter(x => x.title.length > 3);
    }
    return Array.from(items).slice(0, 30).map(el => ({
        title: el.querySelector('a[href*="/p/"], a[class*="title"], .p_title a, a')?.textContent?.trim() || '',
        author: el.querySelector('.p_author, [class*="author"], [class*="user"], [class*="name"]')?.textContent?.trim() || '',
        excerpt: el.querySelector('.p_content, [class*="abstract"], .p_abstract, [class*="content"], [class*="desc"]')?.textContent?.trim()?.slice(0, 200) || '',
        replies: el.querySelector('.p_reply, [class*="reply"], [class*="count"], [class*="num"]')?.textContent?.trim() || '',
        link: el.querySelector('a[href*="/p/"]')?.getAttribute('href') || el.querySelector('a')?.getAttribute('href') || '',
    })).filter(x => x.title.length > 2);
}"""

# 百度站内搜索结果提取（贴吧搜索被百度安全验证拦截时的 fallback）
_BAIDU_TIEBA_JS = """\
() => {
    const results = [];
    const seen = new Set();
    // 百度搜索结果容器
    const containers = document.querySelectorAll('.result, .c-container, [class*="result"]');
    containers.forEach(el => {
        const linkEl = el.querySelector('a[href*="tieba.baidu.com/p/"]');
        if (!linkEl) return;
        const href = linkEl.getAttribute('href') || '';
        if (!href || seen.has(href)) return;
        seen.add(href);
        const title = linkEl.textContent?.trim() || el.querySelector('h3')?.textContent?.trim() || '';
        const excerpt = el.querySelector('.c-abstract, [class*="abstract"], [class*="content"]')?.textContent?.trim()?.slice(0, 200) || '';
        const meta = el.querySelector('.c-showurl, [class*="showurl"], [class*="source"]')?.textContent?.trim() || '';
        results.push({
            title: title,
            author: meta.replace('tieba.baidu.com', '').replace(/[\\/]/g, '').trim(),
            excerpt: excerpt,
            replies: '',
            link: href,
        });
    });
    // 宽泛匹配
    if (results.length === 0) {
        document.querySelectorAll('a[href*="tieba.baidu.com/p/"]').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (!href || seen.has(href)) return;
            seen.add(href);
            results.push({
                title: a.textContent?.trim()?.slice(0, 100) || '',
                author: '',
                excerpt: '',
                replies: '',
                link: href,
            });
        });
    }
    return results;
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
    """搜索贴吧。Path 1: 纯 HTTP Session → Path 2: CDP Browser"""
    logger.info(f"贴吧搜索: keyword={keyword}")

    # Path 1: 纯 HTTP Session（curl_cffi 绕过百度安全验证）
    try:
        from src.utils.session_manager import ensure_session
        if await ensure_session("tieba"):
            from src.utils.tieba_http import search_all
            items = await search_all(keyword, limit=20)
            if items:
                logger.info(f"[tieba-session] 纯HTTP直连成功: {len(items)} 条")
                return json.dumps(items, ensure_ascii=False)
    except Exception as exc:
        logger.warning(f"贴吧 Session HTTP 失败: {exc}，尝试 CDP 浏览器路径")

    # Path 2: CDP Browser
    page = await browser.new_page()
    try:
        await page.goto(
            f"https://tieba.baidu.com/f/search/res?qw={keyword}",
            wait_until="domcontentloaded",
        )
        await page.wait_for_timeout(5000)
        # 检测安全验证
        cur_title = await page.title()
        if "安全验证" in cur_title:
            logger.warning("贴吧搜索: 触发百度安全验证，请先在浏览器中手动访问贴吧完成验证")
            return json.dumps([], ensure_ascii=False)
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
