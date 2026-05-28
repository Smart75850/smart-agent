import asyncio
import json
import re
from typing import Optional
from urllib.parse import quote

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
            author_link: item.querySelector('.bili-video-card__info--author')?.getAttribute('href') || '',
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


async def bilibili_search(keyword: str, count: int = 40) -> str:
    """搜索 B站 关键字 — 纯 HTTP Wbi 签名优先，CDP 浏览器兜底。"""
    logger.info(f"B站搜索: keyword={keyword} count={count}")

    # ── Path 1: 纯 HTTP Wbi 签名（零浏览器）─────────────────
    try:
        from src.utils.bilibili_http import search_all
        items = await search_all(keyword, limit=count)
        if items:
            links_normalized = _normalize_links(items)
            logger.info(f"[bilibili-session] 纯HTTP直连成功: {len(items)} 条")
            return json.dumps(links_normalized, ensure_ascii=False)
        else:
            logger.info(f"[bilibili-session] HTTP搜索返回空，回退 CDP")
    except Exception as exc:
        logger.warning(f"B站 HTTP 搜索失败: {exc}，回退 CDP 浏览器")

    # ── Path 2: CDP 浏览器（兜底）─────────────────────────
    all_items = []
    seen_bvids = set()
    per_page = 42  # B站每页约 42 条

    for page_num in range(1, 15):  # 最多 15 页
        if page_num == 1:
            url = f"https://search.bilibili.com/all?keyword={quote(keyword)}"
        else:
            url = f"https://search.bilibili.com/all?keyword={quote(keyword)}&page={page_num}"

        result = await browser.evaluate(url, _SEARCH_JS)
        if not result:
            break

        new_count = 0
        for item in result:
            link = item.get("link", "")
            bv_match = re.search(r'(BV[a-zA-Z0-9]+)', link)
            bvid = bv_match.group(1) if bv_match else link
            if bvid and bvid not in seen_bvids:
                seen_bvids.add(bvid)
                item["bvid"] = bvid
                all_items.append(item)
                new_count += 1

        if new_count == 0:
            break
        if len(all_items) >= count:
            break

    result = all_items[:count]
    result = _normalize_links(result)
    logger.info(f"B站搜索完成: {len(result)} 條 (翻{page_num}页)")
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
    """爬取 B站 評論，DOM 滚动提取。"""
    logger.info(f"B站評論: bvid={bvid}")
    page = await browser.new_page()
    try:
        await page.goto(f"https://www.bilibili.com/video/{bvid}", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        # 滚动到评论区
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.3)")
        await page.wait_for_timeout(2000)
        # 多次滚动加载更多评论
        for _ in range(5):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)

        result = await page.evaluate("""() => {
    // 尝试从 shadow DOM 提取（B站新版评论组件）
    const biliComments = document.querySelector('bili-comments');
    if (biliComments && biliComments.shadowRoot) {
        const root = biliComments.shadowRoot;
        const threads = root.querySelectorAll('bili-comment-thread-renderer');
        const items = [];
        threads.forEach(thread => {
            if (!thread.shadowRoot) return;
            const renderer = thread.shadowRoot.querySelector('bili-comment-renderer');
            if (!renderer || !renderer.shadowRoot) return;
            const r = renderer.shadowRoot;
            const userInfo = r.querySelector('bili-comment-user-info');
            const richText = r.querySelector('bili-rich-text');
            let user = '', content = '';
            if (userInfo && userInfo.shadowRoot) {
                user = userInfo.shadowRoot.querySelector('#user-name a')?.textContent?.trim() || '';
            }
            if (richText && richText.shadowRoot) {
                content = richText.shadowRoot.querySelector('#contents')?.textContent?.trim() || '';
            }
            if (user || content) items.push({user, content, likes: '', date: ''});
        });
        if (items.length >= 5) return items;
    }

    // fallback: 纯 DOM 提取
    const replyItems = document.querySelectorAll('.reply-item, [class*="reply-item"], [class*="ReplyItem"]');
    if (replyItems.length >= 2) {
        return Array.from(replyItems).slice(0, 40).map(el => ({
            user: el.querySelector('.user-name, [class*="user-name"], [class*="User"]')?.textContent?.trim() || '',
            content: el.querySelector('.reply-content, [class*="content"], .text')?.textContent?.trim() || el.textContent.trim().slice(0, 200),
            likes: '',
            date: '',
        }));
    }

    // last fallback: 抓所有可见文本块
    const allText = document.body.innerText;
    const lines = allText.split('\\n').filter(l => l.trim().length > 10).slice(0, 60);
    return lines.map(l => ({user: '', content: l.trim().slice(0, 200), likes: '', date: ''}));
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
        """() => {
  const midEl = document.querySelector('a[href*="space.bilibili.com"]');
  const midHref = midEl?.getAttribute('href') || '';
  const midMatch = midHref.match(/space\\.bilibili\\.com\\/(\\d+)/);
  return {
    title: document.querySelector('.video-title')?.textContent?.trim() || '',
    desc: document.querySelector('.video-desc')?.textContent?.trim() || '',
    plays: document.querySelector('.video-info-detail .view')?.textContent?.trim() || '',
    likes: document.querySelector('.video-info-detail .like')?.textContent?.trim() || '',
    coins: document.querySelector('.video-info-detail .coin')?.textContent?.trim() || '',
    favs: document.querySelector('.video-info-detail .collect')?.textContent?.trim() || '',
    tags: Array.from(document.querySelectorAll('.tag-area .tag')).map(t => t.textContent.trim()),
    mid: midMatch ? midMatch[1] : '',
  };
}""",
    )
    title = result.get("title", "N/A") if isinstance(result, dict) else "N/A"
    logger.info(f"B站詳情完成: {title} mid={result.get('mid', '?')}")
    return json.dumps(result, ensure_ascii=False)


async def _bilibili_user_cdp(uid: str) -> list[dict]:
    """CDP 方式获取用户视频，一次加载 + reload 重试。"""
    page = await browser.new_page()
    try:
        for attempt in range(2):
            if attempt == 0:
                await page.goto(f"https://space.bilibili.com/{uid}/video", wait_until="domcontentloaded", timeout=30000)
            else:
                logger.warning(f"B站用戶 {uid}: CDP 第1次0条，reload 重试")
                await page.reload(wait_until="domcontentloaded", timeout=30000)

            # 等 .bili-video-card 出现（最多 8s，比固定等待更精准）
            try:
                await page.wait_for_selector(".bili-video-card", timeout=8000)
            except Exception:
                pass
            await page.wait_for_timeout(2000)

            # 滚动触发懒加载
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000)
            await page.wait_for_timeout(1500)

            result = await page.evaluate(_USER_JS)
            if result and len(result) > 0:
                return result

        return []
    finally:
        await page.close()


# 提取用户视频的 JS
_USER_JS = """() => {
    let cards = document.querySelectorAll('.bili-video-card');
    if (cards.length === 0) cards = document.querySelectorAll('.cube-item');
    if (cards.length === 0) cards = document.querySelectorAll('.small-item');
    if (cards.length === 0) cards = document.querySelectorAll('[class*="video-card"]');
    if (cards.length === 0) {
        const bvLinks = document.querySelectorAll('a[href*="/video/BV"]');
        const parents = new Set();
        bvLinks.forEach(a => {
            const card = a.closest('div[class], li[class]');
            if (card) parents.add(card);
        });
        cards = Array.from(parents);
    }
    const seen = new Set();
    return Array.from(cards).map(card => {
        const linkEl = card.querySelector('a[href*="/video/BV"]') || card.querySelector('a');
        const href = linkEl?.getAttribute('href') || '';
        let link = href;
        if (link && link.startsWith('//')) link = 'https:' + link;
        const titleEl = card.querySelector('.title, .bili-video-card__info--tit, [class*="title"], [class*="Title"]');
        const playEl = card.querySelector('.play, .bili-video-card__stats--item:first-child, [class*="play"], [class*="count"], [class*="view"]');
        const durationEl = card.querySelector('.bili-video-card__stats__duration, [class*="duration"]');
        const authorEl = card.querySelector('.bili-video-card__info--author, [class*="author"], [class*="name"]');
        const key = href || titleEl?.textContent?.trim();
        if (!key || seen.has(key)) return null;
        seen.add(key);
        return {
            title: titleEl?.textContent?.trim() || '',
            author: authorEl?.textContent?.trim() || '',
            plays: playEl?.textContent?.trim() || '',
            likes: '',
            duration: durationEl?.textContent?.trim() || '',
            link,
        };
    }).filter(Boolean);
}"""


async def bilibili_user(uid: str) -> str:
    """爬取 B站 用戶主頁視頻列表 — HTTP API 优先，CDP 兜底。"""
    logger.info(f"B站用戶: uid={uid}")

    # Path 1: 纯 HTTP API（零浏览器）
    try:
        from src.utils.bilibili_http import fetch_user_videos
        items = await fetch_user_videos(uid, limit=40)
        if items:
            logger.info(f"B站用戶 HTTP: {len(items)} 條")
            return json.dumps(_normalize_links(items), ensure_ascii=False)
    except Exception as exc:
        logger.warning(f"B站用戶 HTTP 失败: {exc}，回退 CDP")

    # Path 2: CDP 浏览器兜底
    result = await _bilibili_user_cdp(uid)
    logger.info(f"B站用戶 CDP: {len(result)} 條")
    return json.dumps(result, ensure_ascii=False)


class BilibiliAdapter(PlatformAdapter):
    @property
    def name(self) -> str:
        return "bilibili"

    @property
    def need_login(self) -> bool:
        return False

    async def search(self, keyword: str, limit: Optional[int] = None,
                     sort_type: int = 0, publish_time: int = 0,
                     search_channel: str = "") -> list[dict]:
        data = json.loads(await bilibili_search(keyword, count=limit or 40))
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
