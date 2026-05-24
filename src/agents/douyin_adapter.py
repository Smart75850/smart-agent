import json
from typing import Optional

from base.platform_base import PlatformAdapter
from src.utils.browser_service import browser
from src.utils.logger import logger

_SEARCH_JS = """\
() => {
    const cards = document.querySelectorAll('.search-result-card');
    return Array.from(cards).map(card => {
        const texts = Array.from(card.querySelectorAll('a, span, p')).map(el => el.textContent.trim()).filter(Boolean);
        const linkEl = card.querySelector('a[href*="/video/"]');
        return {
            title: texts[2] || null,
            author: texts[4] || null,
            duration: texts[0] || null,
            plays: texts[1] || null,
            date: texts[5] || null,
            link: linkEl?.getAttribute('href') ?? null,
        };
    });
}"""

_USER_JS = """\
() => {
    const containers = document.querySelectorAll('a[href*="/video/"]');
    const seen = new Set();
    const items = [];
    containers.forEach(el => {
        const href = el.getAttribute('href');
        if (!href || seen.has(href)) return;
        seen.add(href);
        const titleEl = el.querySelector('[class*="title"], [class*="Title"], h3, h2, p');
        const playEl = el.querySelector('[class*="play"], [class*="Play"], [class*="count"]');
        const likeEl = el.querySelector('[class*="like"], [class*="Like"], [class*="digg"]');
        items.push({
            title: titleEl?.textContent?.trim() ?? null,
            plays: playEl?.textContent?.trim() ?? null,
            likes: likeEl?.textContent?.trim() ?? null,
            link: href ?? null,
        });
    });
    return items;
}"""


async def douyin_search(keyword: str) -> str:
    logger.info(f"抖音搜索: keyword={keyword}")
    api_url = f"https://www.douyin.com/aweme/v1/web/search/item/?keyword={keyword}&search_source=normal_search&is_filter_search=0&publish_time=30"
    try:
        from src.utils.sign_client import sign, SignSrvUnavailable
        signed = sign(api_url)
        headers = {
            "User-Agent": signed["user_agent"],
            "Cookie": "",
        }
        cookie_parts = []
        if signed.get("ttwid"):
            cookie_parts.append(f"ttwid={signed['ttwid']}")
        if signed.get("ms_token"):
            cookie_parts.append(f"msToken={signed['ms_token']}")
        if cookie_parts:
            headers["Cookie"] = "; ".join(cookie_parts)
        import requests as req
        resp = req.get(signed["signed_url"], headers=headers, timeout=10)
        data = resp.json()
        if data.get("status_code") != 0:
            raise Exception(f"API 返回错误: {data}")
        logger.info(f"抖音搜索完成(SignSrv): {len(data.get('data', []))} 條結果")
        return json.dumps(data, ensure_ascii=False)
    except (Exception, SignSrvUnavailable) as e:
        if isinstance(e, SignSrvUnavailable):
            logger.warning(f"SignSrv 不可用，降级到 CDP 浏览器模式: {e}")
        else:
            logger.warning(f"SignSrv 模式失败，降级到 CDP 浏览器模式: {e}")
        url = f"https://www.douyin.com/search/{keyword}"
        result = await browser.evaluate(url, _SEARCH_JS)
        logger.info(f"抖音搜索完成(CDP降级): {len(result)} 條結果")
        return json.dumps(result, ensure_ascii=False)


async def douyin_user_videos(user_id: str) -> str:
    logger.info(f"抖音用戶視頻: user_id={user_id}")
    api_url = f"https://www.douyin.com/aweme/v1/web/user/profile/other/?sec_user_id={user_id}&publish_video_strategy_type=2"
    try:
        from src.utils.sign_client import sign, SignSrvUnavailable
        signed = sign(api_url)
        headers = {
            "User-Agent": signed["user_agent"],
            "Cookie": "",
        }
        cookie_parts = []
        if signed.get("ttwid"):
            cookie_parts.append(f"ttwid={signed['ttwid']}")
        if signed.get("ms_token"):
            cookie_parts.append(f"msToken={signed['ms_token']}")
        if cookie_parts:
            headers["Cookie"] = "; ".join(cookie_parts)
        import requests as req
        resp = req.get(signed["signed_url"], headers=headers, timeout=10)
        data = resp.json()
        if data.get("status_code") != 0:
            raise Exception(f"API 返回错误: {data}")
        logger.info(f"抖音用戶視頻完成(SignSrv): {len(data.get('data', []))} 條結果")
        return json.dumps(data, ensure_ascii=False)
    except (Exception, SignSrvUnavailable) as e:
        if isinstance(e, SignSrvUnavailable):
            logger.warning(f"SignSrv 不可用，降级到 CDP 浏览器模式: {e}")
        else:
            logger.warning(f"SignSrv 模式失败，降级到 CDP 浏览器模式: {e}")
        url = f"https://www.douyin.com/user/{user_id}"
        result = await browser.evaluate(url, _USER_JS)
        logger.info(f"抖音用戶視頻完成(CDP降级): {len(result)} 條結果")
        return json.dumps(result, ensure_ascii=False)


async def douyin_comment(video_id: str) -> str:
    """爬取抖音視頻評論，需登入先有內容。回傳 JSON 字串。"""
    logger.info(f"抖音評論: video_id={video_id}")
    page = await browser.new_page()
    try:
        await page.goto(f"https://www.douyin.com/video/{video_id}", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        result = await page.evaluate("""() => {
    // 一級評論 container：搵 parent-level comment containers
    const containers = document.querySelectorAll('[class*="commentContainer"], [class*="CommentContainer"], [class*="parent-comment"], [class*="ParentComment"]');
    if (containers.length > 0) {
        const seen = new Set();
        return Array.from(containers).filter(c => {
            const t = c.textContent.trim();
            return t && t.length >= 5 && !seen.has(t) && (seen.add(t), true);
        }).map(c => ({
            content: c.querySelector('[class*="text"], [class*="Text"], [class*="content"], [class*="Content"]')?.textContent?.trim() || c.textContent.trim().slice(0, 200),
            // 🆕 二級評論 — container 內嘅 child comment element
            replies: Array.from(c.querySelectorAll('[class*="sub-comment"], [class*="SubComment"], [class*="reply"], [class*="Reply"]')).map(r => ({
                content: r.querySelector('[class*="text"], [class*="Text"], p')?.textContent?.trim() || r.textContent.trim().slice(0, 200),
            })),
        }));
    }
    // fallback: 原 flat 模式（保留 backward compat）
    const items = document.querySelectorAll('[class*="comment"] [class*="text"], [class*="comment"] p, [class*="Comment"] p');
    const seen = new Set();
    return Array.from(items).filter(el => {
        const t = el.textContent.trim();
        return t && t.length >= 2 && !seen.has(t) && (seen.add(t), true);
    }).map(el => ({ content: el.textContent.trim(), replies: [] }));
}""")
        logger.info(f"抖音評論完成: {len(result)} 條")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


async def douyin_hot() -> str:
    """爬取抖音熱榜，需登入先有完整內容。回傳 JSON 字串。"""
    logger.info("抖音熱榜: 開始爬取")
    page = await browser.new_page()
    try:
        await page.goto("https://www.douyin.com/hot", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        result = await page.evaluate("""() => {
    const items = document.querySelectorAll('[class*="hot"] [class*="title"], [class*="trend"] [class*="title"], [class*="Hot"] [class*="Title"]');
    const seen = new Set();
    return Array.from(items).filter(el => {
        const t = el.textContent.trim();
        if (!t || t.length < 3 || seen.has(t)) return false;
        seen.add(t);
        return true;
    }).map(el => ({ title: el.textContent.trim() }));
}""")
        logger.info(f"抖音熱榜完成: {len(result)} 條")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


async def douyin_detail(video_id: str) -> str:
    """爬取抖音視頻詳情，需登入先有內容。回傳 JSON 字串。"""
    logger.info(f"抖音詳情: video_id={video_id}")
    page = await browser.new_page()
    try:
        await page.goto(f"https://www.douyin.com/video/{video_id}", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        result = await page.evaluate("""() => {
    const titleEl = document.querySelector('[class*="title"], [class*="Title"], h1');
    const descEl = document.querySelector('[class*="desc"], [class*="Desc"], [class*="description"]');
    const playEl = document.querySelector('[class*="play"], [class*="Play"], [class*="count"]');
    const likeEl = document.querySelector('[class*="like"]:not([class*="digg"]), [class*="Like"]');
    const shareEl = document.querySelector('[class*="share"], [class*="Share"]');
    return {
        title: titleEl?.textContent?.trim() || '',
        desc: descEl?.textContent?.trim() || '',
        plays: playEl?.textContent?.trim() || '',
        likes: likeEl?.textContent?.trim() || '',
        shares: shareEl?.textContent?.trim() || '',
    };
}""")
        logger.info(f"抖音詳情完成")
        return json.dumps(result, ensure_ascii=False)
    finally:
        await page.close()


class DouyinAdapter(PlatformAdapter):
    @property
    def name(self) -> str:
        return "douyin"

    @property
    def need_login(self) -> bool:
        return True

    async def search(self, keyword: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await douyin_search(keyword))
        return data[:limit] if limit else data

    async def hot(self, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await douyin_hot())
        return data[:limit] if limit else data

    async def detail(self, item_id: str, **kwargs) -> dict:
        return json.loads(await douyin_detail(item_id))

    async def comment(self, item_id: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await douyin_comment(item_id))
        return data[:limit] if limit else data

    async def user(self, user_id: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await douyin_user_videos(user_id))
        return data[:limit] if limit else data
