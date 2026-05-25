import json
from typing import Optional

from base.platform_base import PlatformAdapter
from src.utils.browser_service import browser
from src.utils.logger import logger

_HOT_JS = """\
() => {
    const items = document.querySelectorAll('.HotItem');
    return Array.from(items).map(item => ({
        rank: item.querySelector('.HotItem-rank')?.textContent?.trim() || '',
        title: item.querySelector('.HotItem-title')?.textContent?.trim() || '',
        excerpt: item.querySelector('.HotItem-excerpt')?.textContent?.trim() || '',
        heat: item.querySelector('.HotItem-metrics')?.textContent?.trim()?.replace(/\\s+/g, '') || '',
        link: item.querySelector('a')?.getAttribute('href') || '',
    }));
}"""

_SEARCH_JS = """\
() => {
    const cards = document.querySelectorAll('[class*="Search"] [class*="Card" i], [class*="SearchResult"], .ContentItem, .AnswerCard, .QuestionCard');
    if (cards.length === 0) {
        const all = document.querySelectorAll('[class*="Card"], [class*="item"]');
        return Array.from(all).slice(0, 30).map(el => ({
            title: el.querySelector('[class*="title"], [class*="Title"], h2, h3')?.textContent?.trim() || '',
            excerpt: el.querySelector('[class*="excerpt"], [class*="summary"], [class*="content"], p')?.textContent?.trim()?.slice(0, 200) || '',
            votes: el.querySelector('[class*="vote"], [class*="like"], [class*="count"], [class*="meta"]')?.textContent?.trim() || '',
            link: el.querySelector('a')?.getAttribute('href') || '',
        })).filter(x => x.title.length > 3);
    }
    const seen = new Set();
    return Array.from(cards).map(card => {
        const titleEl = card.querySelector('[class*="title"], [class*="Title"], h2, h1, h3, [itemprop="name"], a strong, a');
        const excerptEl = card.querySelector('[class*="excerpt"], [class*="summary"], [class*="content"], [class*="RichText"], p');
        const metaEl = card.querySelector('[class*="vote"], [class*="like"], [class*="count"], [class*="meta"], [class*="actions"], [class*="Number"], [class*="Hot"], [class*="metrics"]');
        const linkEl = card.querySelector('a[href*="/question/"], a[href*="/answer/"], a[href*="/pin/"], a[href*="/hot/"], a[href*="/roundtable/"], a[href*="/zhuanlan/"], a[href]');
        const title = titleEl?.textContent?.trim() || '';
        if (!title || title.length < 3 || seen.has(title)) return null;
        seen.add(title);
        return {
            title,
            excerpt: excerptEl?.textContent?.trim()?.slice(0, 300) || '',
            votes: metaEl?.textContent?.trim() || '',
            link: linkEl?.getAttribute('href') || '',
        };
    }).filter(Boolean);
}"""


async def zhihu_hot() -> str:
    """爬取知乎熱榜，需登入先有內容（未登入跳轉 signin）。回傳 JSON 字串。"""
    logger.info("知乎熱榜: 開始爬取")
    page = await browser.new_page()
    try:
        await page.goto("https://www.zhihu.com/hot", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        result = await page.evaluate(_HOT_JS)
        logger.info(f"知乎熱榜完成: {len(result)} 條結果")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


async def zhihu_comment(question_id: str) -> str:
    """爬取知乎問題評論，需登入先有完整內容。回傳 JSON 字串。"""
    logger.info(f"知乎評論: question_id={question_id}")
    page = await browser.new_page()
    try:
        await page.goto(f"https://www.zhihu.com/question/{question_id}", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        result = await page.evaluate("""() => {
    const items = document.querySelectorAll('.CommentItem');
    return Array.from(items).map(item => ({
        user: item.querySelector('.CommentItem-UserLink')?.textContent?.trim() || '',
        content: item.querySelector('.CommentItem-content')?.textContent?.trim() || '',
        likes: item.querySelector('.CommentItem-like')?.textContent?.trim() || '',
        // 🆕 二級評論
        replies: Array.from(item.querySelectorAll('.CommentItem-reply')).map(r => ({
            user: r.querySelector('.CommentItem-UserLink')?.textContent?.trim() || '',
            content: r.querySelector('.CommentItem-content')?.textContent?.trim() || '',
            likes: r.querySelector('.CommentItem-like')?.textContent?.trim() || '',
        })),
    }));
}""")
        logger.info(f"知乎評論完成: {len(result)} 條")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


async def zhihu_detail(question_id: str) -> str:
    """爬取知乎問題詳情 + 精選回答，需登入先有完整內容。回傳 JSON 字串。"""
    logger.info(f"知乎詳情: question_id={question_id}")
    page = await browser.new_page()
    try:
        await page.goto(f"https://www.zhihu.com/question/{question_id}", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        result = await page.evaluate("""() => {
    const titleEl = document.querySelector('.QuestionItem-title, .QuestionHeader-title, [class*="QuestionTitle"]');
    const descEl = document.querySelector('.QuestionItem-desc, .QuestionHeader-detail, [class*="QuestionDetail"]');
    const answers = document.querySelectorAll('.AnswerCard, [class*="AnswerItem"]');
    return {
        title: titleEl?.textContent?.trim() || '',
        desc: descEl?.textContent?.trim() || '',
        answer_count: document.querySelector('.QuestionItem-answers, .List-headerText')?.textContent?.trim() || '',
        top_answers: Array.from(answers).slice(0, 5).map(a => {
            const authorLink = a.querySelector('a[href*="/people/"], a[href*="/org/"]');
            return {
                author: a.querySelector('.AuthorInfo-name, .UserItem-name, [class*="author"] [class*="name"]')?.textContent?.trim() || '',
                author_url: authorLink?.getAttribute('href') || '',
                content: a.querySelector('.RichContent-inner, .RichText')?.textContent?.trim()?.slice(0, 500) || '',
                votes: a.querySelector('.Voters, .Button--vote')?.textContent?.trim() || '',
            };
        }),
    };
}""")
        title = result.get("title", "N/A") if isinstance(result, dict) else "N/A"
        logger.info(f"知乎詳情完成: {title}")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


async def zhihu_user(user_id: str) -> str:
    """爬取知乎用戶主頁內容，需登入先有完整內容。回傳 JSON 字串。"""
    logger.info(f"知乎用戶: user_id={user_id}")
    page = await browser.new_page()
    try:
        await page.goto(f"https://www.zhihu.com/people/{user_id}", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        result = await page.evaluate("""() => {
    const items = document.querySelectorAll('.ProfileItem, .ContentItem, [class*="Profile"] [class*="item"]');
    const seen = new Set();
    return Array.from(items).filter(el => {
        const t = el.textContent.trim();
        if (!t || t.length < 5 || seen.has(t)) return false;
        seen.add(t);
        return true;
    }).slice(0, 20).map(el => ({
        title: el.querySelector('[class*="title"], h2')?.textContent?.trim() || '',
        excerpt: el.querySelector('[class*="excerpt"], [class*="summary"]')?.textContent?.trim() || '',
        link: el.querySelector('a')?.getAttribute('href') || '',
    }));
}""")
        logger.info(f"知乎用戶完成: {len(result)} 條")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


class ZhihuAdapter(PlatformAdapter):
    @property
    def name(self) -> str:
        return "zhihu"

    @property
    def need_login(self) -> bool:
        return True

    async def search(self, keyword: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await zhihu_search(keyword))
        return data[:limit] if limit else data

    async def hot(self, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await zhihu_hot())
        return data[:limit] if limit else data

    async def detail(self, item_id: str, **kwargs) -> dict:
        return json.loads(await zhihu_detail(item_id))

    async def comment(self, item_id: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await zhihu_comment(item_id))
        return data[:limit] if limit else data

    async def user(self, user_id: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await zhihu_user(user_id))
        return data[:limit] if limit else data


async def zhihu_search(keyword: str) -> str:
    """搜索知乎內容，需登入先有完整結果。回傳 JSON 字串。"""
    logger.info(f"知乎搜索: keyword={keyword}")
    page = await browser.new_page()
    try:
        await page.goto(
            f"https://www.zhihu.com/search?type=content&q={keyword}",
            wait_until="domcontentloaded",
        )
        await page.wait_for_timeout(5000)
        result = await page.evaluate(_SEARCH_JS)
        logger.info(f"知乎搜索完成: {len(result)} 條結果")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()
