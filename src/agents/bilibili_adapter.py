import json
from typing import Optional

from base.platform_base import PlatformAdapter
from src.utils.browser_service import browser
from src.utils.logger import logger


_RANK_JS = """\
() => {
    const items = document.querySelectorAll('.rank-list .rank-item');
    return Array.from(items).map(item => {
        const statBoxes = item.querySelectorAll('.detail .data-box:not(.up-name)');
        return {
            rank: item.querySelector('.num span')?.textContent?.trim(),
            title: item.querySelector('.info .title')?.textContent?.trim(),
            author: item.querySelector('.up-name')?.textContent?.trim(),
            play_count: statBoxes[0]?.textContent?.trim(),
            likes: statBoxes[1]?.textContent?.trim(),
            link: item.querySelector('.info a')?.getAttribute('href'),
        };
    });
}"""

_SEARCH_JS = """\
() => {
    const items = document.querySelectorAll('.bili-video-card');
    return Array.from(items).map(item => {
        const statItems = item.querySelectorAll('.bili-video-card__stats--item');
        return {
            title: item.querySelector('.bili-video-card__info--tit')?.textContent?.trim(),
            author: item.querySelector('.bili-video-card__info--author')?.textContent?.trim(),
            play_count: statItems[0]?.textContent?.trim(),
            likes: statItems[1]?.textContent?.trim(),
            duration: item.querySelector('.bili-video-card__stats__duration')?.textContent?.trim(),
            link: item.querySelector('a')?.getAttribute('href'),
        };
    });
}"""


async def bilibili_rank(category: str = "all") -> str:
    """爬取 B站 排行榜指定分類，回傳 JSON 字串。"""
    logger.info(f"B站排行榜: category={category}")
    url = f"https://www.bilibili.com/v/popular/rank/{category}"
    result = await browser.evaluate(url, _RANK_JS, wait_selector=".rank-list")
    result = _normalize_links(result)
    logger.info(f"B站排行榜完成: {len(result)} 條結果")
    return json.dumps(result, ensure_ascii=False)


async def bilibili_search(keyword: str) -> str:
    """搜索 B站 關鍵字，回傳 JSON 字串。"""
    logger.info(f"B站搜索: keyword={keyword}")
    url = f"https://search.bilibili.com/all?keyword={keyword}"
    result = await browser.evaluate(url, _SEARCH_JS, wait_selector=".bili-video-card")
    result = _normalize_links(result)
    logger.info(f"B站搜索完成: {len(result)} 條結果")
    return json.dumps(result, ensure_ascii=False)


def _normalize(link: str) -> str:
    if link.startswith("//"):
        return "https:" + link
    return link


def _normalize_links(data: list[dict]) -> list[dict]:
    for row in data:
        if "link" in row and isinstance(row["link"], str):
            row["link"] = _normalize(row["link"])
    return data


async def bilibili_comment(bvid: str) -> str:
    logger.info(f"B站評論: bvid={bvid}")
    page = await browser.new_page()
    try:
        await page.goto(f"https://www.bilibili.com/video/{bvid}", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(3000)

        result = await page.evaluate("""() => {
    const el = document.querySelector('bili-comments');
    if (!el || !el.shadowRoot) return [];

    const threads = el.shadowRoot.querySelectorAll('bili-comment-thread-renderer');
    const results = [];

    threads.forEach(thread => {
        if (!thread.shadowRoot) return;
        const renderer = thread.shadowRoot.querySelector('bili-comment-renderer');
        if (!renderer || !renderer.shadowRoot) return;
        const root = renderer.shadowRoot;

        const userInfo = root.querySelector('bili-comment-user-info');
        let user = '';
        if (userInfo && userInfo.shadowRoot) {
            const nameEl = userInfo.shadowRoot.querySelector('#user-name a');
            if (nameEl) user = nameEl.textContent.trim();
        }

        const richText = root.querySelector('bili-rich-text');
        let content = '';
        if (richText && richText.shadowRoot) {
            const contentsEl = richText.shadowRoot.querySelector('#contents');
            if (contentsEl) content = contentsEl.textContent.trim();
        }

        const actions = root.querySelector('bili-comment-action-buttons-renderer');
        let likes = '', date = '';
        if (actions && actions.shadowRoot) {
            const likeEl = actions.shadowRoot.querySelector('#like #count');
            if (likeEl) likes = likeEl.textContent.trim();
            const dateEl = actions.shadowRoot.querySelector('#pubdate');
            if (dateEl) date = dateEl.textContent.trim();
        }

        // 🆕 二級評論 — 遍歷 thread 內所有 reply renderer
        const replies = [];
        const replyRenderers = thread.shadowRoot.querySelectorAll('bili-comment-reply-renderer');
        if (replyRenderers.length === 0) {
            // fallback: bili-comment-replies-renderer 可能包住 reply
            const rr = thread.shadowRoot.querySelector('bili-comment-replies-renderer');
            if (rr && rr.shadowRoot) {
                rr.shadowRoot.querySelectorAll('bili-comment-reply-renderer').forEach(r => {
                    if (!r.shadowRoot) return;
                    const s = r.shadowRoot;
                    const ru = s.querySelector('bili-comment-user-info');
                    const rt = s.querySelector('bili-rich-text');
                    const rl = s.querySelector('bili-comment-action-buttons-renderer');
                    replies.push({
                        user: ru?.shadowRoot?.querySelector('#user-name a')?.textContent?.trim() || '',
                        content: rt?.shadowRoot?.querySelector('#contents')?.textContent?.trim() || '',
                        likes: rl?.shadowRoot?.querySelector('#like #count')?.textContent?.trim() || '',
                    });
                });
            }
        } else {
            replyRenderers.forEach(r => {
                if (!r.shadowRoot) return;
                const s = r.shadowRoot;
                const ru = s.querySelector('bili-comment-user-info');
                const rt = s.querySelector('bili-rich-text');
                const rl = s.querySelector('bili-comment-action-buttons-renderer');
                replies.push({
                    user: ru?.shadowRoot?.querySelector('#user-name a')?.textContent?.trim() || '',
                    content: rt?.shadowRoot?.querySelector('#contents')?.textContent?.trim() || '',
                    likes: rl?.shadowRoot?.querySelector('#like #count')?.textContent?.trim() || '',
                });
            });
        }

        results.push({ user, content, likes, date, replies });
    });

    return results;
}""")
        logger.info(f"B站評論完成: {len(result)} 條")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


async def bilibili_detail(bvid: str) -> str:
    """爬取 B站 視頻詳情，回傳 JSON 字串。"""
    logger.info(f"B站詳情: bvid={bvid}")
    result = await browser.evaluate(
        f"https://www.bilibili.com/video/{bvid}",
        """() => ({
  title: document.querySelector('.video-title')?.textContent?.trim() || '',
  desc: document.querySelector('.video-desc')?.textContent?.trim() || '',
  plays: document.querySelector('.video-info-detail .view')?.textContent?.trim() || '',
  likes: document.querySelector('.video-info-detail .like')?.textContent?.trim() || '',
  coins: document.querySelector('.video-info-detail .coin')?.textContent?.trim() || '',
  favs: document.querySelector('.video-info-detail .collect')?.textContent?.trim() || '',
  tags: Array.from(document.querySelectorAll('.tag-area .tag')).map(t => t.textContent.trim()),
})""",
    )
    title = result.get("title", "N/A") if isinstance(result, dict) else "N/A"
    logger.info(f"B站詳情完成: {title}")
    return json.dumps(result, ensure_ascii=False)


async def bilibili_user(uid: str) -> str:
    """爬取 B站 用戶主頁視頻列表，回傳 JSON 字串。"""
    logger.info(f"B站用戶: uid={uid}")
    page = await browser.new_page()
    try:
        await page.goto(f"https://space.bilibili.com/{uid}/video", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        result = await page.evaluate("""() => {
    const cards = document.querySelectorAll('.small-item');
    return Array.from(cards).map(card => {
        let link = card.querySelector('a')?.getAttribute('href') || '';
        if (link.startsWith('//')) link = 'https:' + link;
        return {
            title: card.querySelector('.title')?.textContent?.trim() || '',
            plays: card.querySelector('.play')?.textContent?.trim() || '',
            comments: card.querySelector('.comment')?.textContent?.trim() || '',
            link,
        };
    });
}""")
        logger.info(f"B站用戶完成: {len(result)} 條")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


class BilibiliAdapter(PlatformAdapter):
    @property
    def name(self) -> str:
        return "bilibili"

    @property
    def need_login(self) -> bool:
        return False

    async def search(self, keyword: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await bilibili_search(keyword))
        return data[:limit] if limit else data

    async def hot(self, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await bilibili_rank("all"))
        return data[:limit] if limit else data

    async def detail(self, item_id: str, **kwargs) -> dict:
        return json.loads(await bilibili_detail(item_id))

    async def comment(self, item_id: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await bilibili_comment(item_id))
        return data[:limit] if limit else data

    async def user(self, user_id: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await bilibili_user(user_id))
        return data[:limit] if limit else data
