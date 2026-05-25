import json
import os
import time
from typing import Optional
from urllib.parse import quote

import requests as http_requests

from base.platform_base import PlatformAdapter
from src.utils.browser_service import browser
from src.utils.douyin_signer import get_signer
from src.utils.logger import logger

_COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "output", "douyin_cookies.json")

_BASE_API_PARAMS = (
    "device_platform=webapp&aid=6383&channel=channel_pc_web"
    "&pc_client_type=1&pc_libra_divert=Windows"
    "&update_version_code=170400&version_code=170400"
    "&version_name=17.4.0&cookie_enabled=true"
    "&screen_width=1920&screen_height=1080"
    "&browser_language=zh-CN&browser_platform=Win32"
    "&browser_name=Chrome&browser_version=123.0.0.0"
    "&browser_online=true&engine_name=Blink&engine_version=123.0.0.0"
    "&os_name=Windows&os_version=10&cpu_core_num=16"
    "&device_memory=8&platform=PC&downlink=10&effective_type=4g&round_trip_time=50"
)

_COMMENT_API_PARAMS = (
    _BASE_API_PARAMS
    + "&item_type=0&insert_ids=&whale_cut_token=&cut_version=1&rcFT="
)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

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


async def douyin_search(keyword: str, count: int = 40) -> str:
    """抖音搜索 — 本地 a_bogus 签名 + offset 翻页，失败降级到 CDP DOM"""
    logger.info(f"抖音搜索: keyword={keyword} count={count}")

    # ① 尝试 API 方式（本地签名 + offset 翻页）
    try:
        cookies = _load_cookies()
        if not cookies:
            raise Exception("未找到 douyin_cookies.json，跳过 API 模式")
        result = _api_search(keyword, count, cookies)
        data = json.loads(result)
        if len(data) == 0:
            raise Exception("API 返回 0 条结果，降级到 CDP DOM")
        return result
    except Exception as e:
        logger.warning(f"API 搜索失败，降级到 CDP DOM: {e}")

    # ② 降级到 CDP DOM 抓取
    url = f"https://www.douyin.com/search/{keyword}"
    result = await browser.evaluate(url, _SEARCH_JS)
    logger.info(f"抖音搜索完成(CDP降级): {len(result)} 條")
    return json.dumps(result, ensure_ascii=False)


def _api_search(keyword: str, count: int, cookies: dict) -> str:
    """用搜索 API + offset 翻页获取多条结果"""
    signer = get_signer()
    ms_token = signer.generate_ms_token()
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())

    all_results = []
    offset = 0
    max_pages = (count // 10) + 2

    for _ in range(max_pages):
        base_url = (
            f"https://www.douyin.com/aweme/v1/web/search/item/?"
            f"{_BASE_API_PARAMS}&keyword={quote(keyword)}"
            f"&offset={offset}&count=10&search_source=normal_search"
            f"&is_filter_search=0&msToken={ms_token}"
        )
        signed_url = base_url + "&a_bogus=" + signer.sign(base_url, _UA)

        headers = {
            "User-Agent": _UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": f"https://www.douyin.com/search/{quote(keyword)}",
            "Cookie": cookie_str,
        }
        resp = http_requests.get(signed_url, headers=headers, timeout=15, verify=False)
        data = resp.json()

        if data.get("status_code") != 0:
            logger.warning(f"搜索 API 返回错误: status_code={data.get('status_code')}")
            break

        for item in (data.get("data") or []):
            info = item.get("aweme_info", item)
            author = info.get("author", {}) or {}
            stat = info.get("statistics", {}) or {}
            all_results.append({
                "title": info.get("desc", ""),
                "author": author.get("nickname", ""),
                "plays": stat.get("play_count", 0),
                "likes": stat.get("digg_count", 0),
                "aweme_id": info.get("aweme_id", ""),
            })

        offset = data.get("cursor", offset + 10)
        has_more = data.get("has_more", 0)
        if not has_more or len(all_results) >= count:
            break
        time.sleep(0.5)

    result = all_results[:count]
    logger.info(f"抖音搜索(API)完成: {len(result)} 條")
    return json.dumps(result, ensure_ascii=False)


def _api_user_videos(user_id: str, cookies: dict) -> str:
    """用用户 API 获取用户视频列表"""
    signer = get_signer()
    ms_token = signer.generate_ms_token()
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())

    base_url = (
        f"https://www.douyin.com/aweme/v1/web/user/profile/other/?"
        f"{_BASE_API_PARAMS}&sec_user_id={user_id}"
        f"&publish_video_strategy_type=2&personal_center_strategy=1"
        f"&msToken={ms_token}"
    )
    signed_url = base_url + "&a_bogus=" + signer.sign(base_url, _UA)

    headers = {
        "User-Agent": _UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": f"https://www.douyin.com/user/{user_id}",
        "Cookie": cookie_str,
    }
    resp = http_requests.get(signed_url, headers=headers, timeout=15, verify=False)
    data = resp.json()

    if data.get("status_code") != 0:
        raise Exception(f"用户 API 返回错误: status_code={data.get('status_code')}")

    user_data = data.get("user", {}) or {}
    items = []
    for item in (data.get("aweme_list") or data.get("data") or []):
        aweme = item.get("aweme_info", item)
        author = aweme.get("author", {}) or {}
        stat = aweme.get("statistics", {}) or {}
        items.append({
            "title": aweme.get("desc", ""),
            "author": author.get("nickname", user_data.get("nickname", "")),
            "plays": stat.get("play_count", 0),
            "likes": stat.get("digg_count", 0),
            "aweme_id": aweme.get("aweme_id", ""),
        })
    logger.info(f"抖音用戶視頻(API)完成: {len(items)} 條")
    return json.dumps(items, ensure_ascii=False)


async def douyin_user_videos(user_id: str) -> str:
    """抖音用户视频 — 本地签名 + API，失败降级到 CDP DOM"""
    logger.info(f"抖音用戶視頻: user_id={user_id}")

    # ① 尝试 API 方式
    try:
        cookies = _load_cookies()
        if not cookies:
            raise Exception("未找到 douyin_cookies.json，跳过 API 模式")
        return _api_user_videos(user_id, cookies)
    except Exception as e:
        logger.warning(f"API 用户视频失败，降级到 CDP DOM: {e}")

    # ② 降级到 CDP DOM 抓取
    url = f"https://www.douyin.com/user/{user_id}"
    result = await browser.evaluate(url, _USER_JS)
    logger.info(f"抖音用戶視頻完成(CDP降级): {len(result)} 條結果")
    return json.dumps(result, ensure_ascii=False)


async def douyin_comment(video_id: str, count: int = 50) -> str:
    """抖音视频评论 — API 优先（使用本地 a_bogus 签名 + cursor 翻页），失败降级到 CDP DOM 抓取"""
    logger.info(f"抖音評論: video_id={video_id} count={count}")

    # ① 尝试 API 方式
    try:
        cookies = _load_cookies()
        if cookies:
            return _api_comment(video_id, count, cookies)
    except Exception as e:
        logger.warning(f"API 评论失败，降级到 CDP DOM: {e}")

    # ② 降级到 CDP DOM 抓取
    return await _dom_comment(video_id)


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


def _load_cookies() -> dict:
    """从保存的 cookie 文件加载"""
    if not os.path.exists(_COOKIE_FILE):
        return {}
    with open(_COOKIE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _api_comment(video_id: str, count: int, cookies: dict) -> str:
    """用评论 API 获取评论，支持 cursor 翻页"""
    signer = get_signer()
    ms_token = signer.generate_ms_token()
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())

    all_comments = []
    cursor = 0
    max_pages = (count // 20) + 2  # 每页 20 条，多加一页缓冲

    for _ in range(max_pages):
        base_url = (
            f"https://www.douyin.com/aweme/v1/web/comment/list/?"
            f"{_COMMENT_API_PARAMS}&aweme_id={video_id}"
            f"&cursor={cursor}&count=20&msToken={ms_token}"
        )
        signed_url = base_url + "&a_bogus=" + signer.sign(base_url, _UA)

        headers = {
            "User-Agent": _UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": f"https://www.douyin.com/video/{video_id}",
            "Cookie": cookie_str,
        }
        resp = http_requests.get(signed_url, headers=headers, timeout=15, verify=False)
        data = resp.json()

        if data.get("status_code") != 0:
            logger.warning(f"评论 API 返回错误: status_code={data.get('status_code')}")
            break

        comments = data.get("comments") or []
        for c in comments:
            text = c.get("text", "")
            user = c.get("user", {}).get("nickname", "")
            likes = c.get("digg_count", 0)
            replies_data = c.get("reply_comment") or []
            replies = [{"user": r.get("user", {}).get("nickname", ""),
                        "content": r.get("text", ""),
                        "likes": r.get("digg_count", 0)}
                       for r in replies_data]
            all_comments.append({
                "user": user,
                "content": text,
                "likes": likes,
                "replies": replies,
            })

        cursor = data.get("cursor", cursor + 20)
        has_more = data.get("has_more", 0)
        if not has_more or len(all_comments) >= count:
            break
        time.sleep(0.5)

    result = all_comments[:count]
    logger.info(f"抖音評論(API)完成: {len(result)} 條")
    return json.dumps(result, ensure_ascii=False)


async def _dom_comment(video_id: str) -> str:
    """CDP DOM 抓取 — 旧方式降级"""
    page = await browser.new_page()
    try:
        await page.goto(f"https://www.douyin.com/video/{video_id}", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        result = await page.evaluate("""() => {
    const containers = document.querySelectorAll('[class*="commentContainer"], [class*="CommentContainer"], [class*="parent-comment"], [class*="ParentComment"]');
    if (containers.length > 0) {
        const seen = new Set();
        return Array.from(containers).filter(c => {
            const t = c.textContent.trim();
            return t && t.length >= 5 && !seen.has(t) && (seen.add(t), true);
        }).map(c => ({
            content: c.querySelector('[class*="text"], [class*="Text"], [class*="content"], [class*="Content"]')?.textContent?.trim() || c.textContent.trim().slice(0, 200),
            replies: Array.from(c.querySelectorAll('[class*="sub-comment"], [class*="SubComment"], [class*="reply"], [class*="Reply"]')).map(r => ({
                content: r.querySelector('[class*="text"], [class*="Text"], p')?.textContent?.trim() || r.textContent.trim().slice(0, 200),
            })),
        }));
    }
    const items = document.querySelectorAll('[class*="comment"] [class*="text"], [class*="comment"] p, [class*="Comment"] p');
    const seen = new Set();
    return Array.from(items).filter(el => {
        const t = el.textContent.trim();
        return t && t.length >= 2 && !seen.has(t) && (seen.add(t), true);
    }).map(el => ({ content: el.textContent.trim(), replies: [] }));
}""")
        logger.info(f"抖音評論(CDP降级)完成: {len(result)} 條")
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
        data = json.loads(await douyin_search(keyword, count=limit or 40))
        return data[:limit] if limit else data

    async def hot(self, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await douyin_hot())
        return data[:limit] if limit else data

    async def detail(self, item_id: str, **kwargs) -> dict:
        return json.loads(await douyin_detail(item_id))

    async def comment(self, item_id: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await douyin_comment(item_id, count=limit or 50))
        return data[:limit] if limit else data

    async def user(self, user_id: str, limit: Optional[int] = None) -> list[dict]:
        data = json.loads(await douyin_user_videos(user_id))
        return data[:limit] if limit else data
