import json
from typing import Optional

from base.platform_base import PlatformAdapter
from src.agents.base_adapter import JsonAdapterMixin
from src.utils.browser_service import browser
from src.utils.logger import logger

_HOT_JS = """\
() => {
    const seen = new Set();
    const seenLinks = new Set();
    const result = [];

    // 热榜页专用: .topic-list 列表
    const topicItems = document.querySelectorAll('.topic-list [class*="item"], [class*="topic"] [class*="item"], [class*="hot-list"] li, [class*="hotTopic"] [class*="item"]');
    for (const el of topicItems) {
        const a = el.querySelector('a[href*="/p/"], a[href*="/f?kw="], a');
        const href = a?.getAttribute('href') || '';
        const title = a?.textContent?.trim() || el.textContent.trim().slice(0, 80);
        const key = href || title;
        if (!key || key.length < 2 || seen.has(key) || seenLinks.has(href)) continue;
        seen.add(key);
        if (href) seenLinks.add(href);
        result.push({
            title,
            author: el.querySelector('[class*="author"], [class*="user"], [class*="name"]')?.textContent?.trim() || '',
            replies: el.querySelector('[class*="reply"], [class*="count"], [class*="num"]')?.textContent?.trim() || '',
            link: href.startsWith('http') ? href : 'https://tieba.baidu.com' + href,
            plays: el.querySelector('[class*="reply"], [class*="count"], [class*="num"]')?.textContent?.trim() || '',
        });
    }

    // 兜底: threadlist 表格样式
    if (result.length < 5) {
        const threads = document.querySelectorAll('.threadlist_title, .j_thread_list, [class*="thread"]');
        for (const el of threads) {
            const a = el.querySelector('.threadlist_title a, a[class*="title"], a[href*="/p/"]') || el.querySelector('a');
            const href = a?.getAttribute('href') || '';
            const title = a?.textContent?.trim() || '';
            const key = href || title;
            if (!key || key.length < 2 || seen.has(key) || seenLinks.has(href)) continue;
            seen.add(key);
            if (href) seenLinks.add(href);
            result.push({
                title,
                author: el.querySelector('.threadlist_author, .frs-author-name, [class*="author"]')?.textContent?.trim() || '',
                replies: el.querySelector('.threadlist_rep_num, [class*="reply"]')?.textContent?.trim() || '',
                link: href.startsWith('http') ? href : 'https://tieba.baidu.com' + href,
                plays: el.querySelector('.threadlist_rep_num, [class*="reply"]')?.textContent?.trim() || '',
            });
        }
    }

    // 兜底2: 任意卡片
    if (result.length < 5) {
        const cards = document.querySelectorAll('[class*="card"], [class*="item"], li');
        for (const el of cards) {
            const a = el.querySelector('a[href*="/p/"], a[href*="/f?kw="], a');
            const href = a?.getAttribute('href') || '';
            const title = a?.textContent?.trim() || el.textContent.trim().slice(0, 80);
            const key = href || title;
            if (!key || key.length < 3 || seen.has(key) || seenLinks.has(href)) continue;
            seen.add(key);
            if (href) seenLinks.add(href);
            result.push({
                title,
                author: el.querySelector('[class*="author"], [class*="user"], [class*="name"]')?.textContent?.trim() || '',
                replies: el.querySelector('[class*="reply"], [class*="count"], [class*="num"]')?.textContent?.trim() || '',
                link: href.startsWith('http') ? href : 'https://tieba.baidu.com' + href,
                plays: el.querySelector('[class*="reply"], [class*="count"], [class*="num"]')?.textContent?.trim() || '',
            });
        }
    }

    return result.slice(0, 30);
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
    try:
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
    except Exception as e:
        logger.warning(f"贴吧热榜异常: {e}")
        return json.dumps([], ensure_ascii=False)


async def tieba_search(keyword: str, count: int = 40) -> str:
    """搜索贴吧。Path 1: 纯 HTTP Session → Path 2: CDP Browser"""
    logger.info(f"贴吧搜索: keyword={keyword} count={count}")

    # Path 1: 纯 HTTP Session（curl_cffi 绕过百度安全验证）
    try:
        from src.utils.session_manager import ensure_session
        if await ensure_session("tieba"):
            from src.utils.tieba_http import search_all
            items = await search_all(keyword, limit=count)
            if items:
                logger.info(f"[tieba-session] 纯HTTP直连成功: {len(items)} 条")
                return json.dumps(items, ensure_ascii=False)
    except Exception as exc:
        logger.warning(f"贴吧 Session HTTP 失败: {exc}，尝试 CDP 浏览器路径")

    # Path 2: CDP Browser
    try:
        page = await browser.new_page()
        try:
            all_items = []
            seen = set()
            max_pages = max(count // 20 + 3, 5)
            for pn in range(0, max_pages):
                url = f"https://tieba.baidu.com/f/search/res?qw={keyword}" if pn == 0 else f"https://tieba.baidu.com/f/search/res?qw={keyword}&pn={pn * 20}"
                await page.goto(url, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)
                cur_title = await page.title()
                if "安全验证" in cur_title:
                    logger.warning("贴吧搜索: 触发百度安全验证，请先在浏览器中手动访问贴吧完成验证")
                    break
                result = await page.evaluate(_SEARCH_JS)
                if not result:
                    break
                new_count = 0
                for item in result:
                    key = item.get("link", "") or item.get("title", "")
                    if key and key not in seen:
                        seen.add(key)
                        all_items.append(item)
                        new_count += 1
                if new_count == 0:
                    break
                if len(all_items) >= count:
                    break
            logger.info(f"贴吧搜索完成: {len(all_items)} 条结果")
            return json.dumps(all_items[:count], ensure_ascii=False)
        finally:
            await page.close()
    except Exception as e:
        logger.warning(f"贴吧搜索 CDP 异常: {e}")
        return json.dumps([], ensure_ascii=False)


async def tieba_detail(tid: str) -> str:
    logger.info(f"贴吧详情: tid={tid}")
    try:
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
    except Exception as e:
        logger.warning(f"贴吧详情异常: {e}")
        return json.dumps({}, ensure_ascii=False)


async def tieba_comment(tid: str) -> str:
    logger.info(f"贴吧评论: tid={tid}")
    try:
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
    except Exception as e:
        logger.warning(f"贴吧评论异常: {e}")
        return json.dumps([], ensure_ascii=False)


async def tieba_user(user_id: str) -> str:
    logger.info(f"贴吧用户: user_id={user_id}")
    try:
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
    except Exception as e:
        logger.warning(f"贴吧用户异常: {e}")
        return json.dumps([], ensure_ascii=False)


class TiebaAdapter(JsonAdapterMixin, PlatformAdapter):
    @property
    def name(self) -> str:
        return "tieba"

    @property
    def need_login(self) -> bool:
        return False

    async def search(self, keyword: str, limit: Optional[int] = None,
                     sort_type: int = 0, publish_time: int = 0,
                     search_channel: str = "") -> list[dict]:
        return self._unwrap(await tieba_search(keyword, count=limit or 40), limit)

    async def hot(self, limit: Optional[int] = None) -> list[dict]:
        return self._unwrap(await tieba_hot(), limit)

    async def detail(self, item_id: str, **kwargs) -> dict:
        return self._unwrap_dict(await tieba_detail(item_id))

    async def comment(self, item_id: str, limit: Optional[int] = None) -> list[dict]:
        return self._unwrap(await tieba_comment(item_id), limit)

    async def user(self, user_id: str, limit: Optional[int] = None) -> list[dict]:
        return self._unwrap(await tieba_user(user_id), limit)
