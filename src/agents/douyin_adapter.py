import asyncio
import json
import os
import httpx
import time
import random
from typing import Optional
from urllib.parse import urlencode, quote

from base.platform_base import PlatformAdapter
from config.settings import settings
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
        items.push({
            title: titleEl?.textContent?.trim() ?? null,
            plays: playEl?.textContent?.trim() ?? null,
            link: href ?? null,
        });
    });
    return items;
}"""


def _load_cookies(platform: str) -> list[dict]:
    """从 CookieBridge 保存的文件加载 cookies。"""
    path = os.path.join(settings.COOKIE_DIR, f"cookies_{platform}.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _find_cookie(cookies: list[dict], name: str) -> str:
    for c in cookies:
        if c.get("name") == name:
            return c.get("value", "")
    return ""


def _build_cookie_str(cookies: list[dict]) -> str:
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name") and c.get("value"))


async def _douyin_search_http(keyword: str, count: int = 40) -> str:
    """SignSrv 直连模式：httpx + a_bogus 签名，不用浏览器。

    需要 CookieBridge 同步过的 Cookies（browser_data/douyin_cookies.json）。
    若无 Cookies，自动回退到 CDP 浏览器模式。
    """
    cookies = _load_cookies("douyin")
    if not cookies:
        logger.info("[douyin-http] 无 douyin cookies，回退浏览器模式")
        return ""

    ttwid = _find_cookie(cookies, "ttwid")
    if not ttwid:
        logger.info("[douyin-http] cookies 中无 ttwid，回退浏览器模式")
        return ""

    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    cookie_str = _build_cookie_str(cookies)
    ms_token = "".join(random.choices("ABCDEFGHIGKLMNOPQRSTUVWXYZabcdefghigklmnopqrstuvwxyz0123456789=", k=107))

    base_url = "https://www.douyin.com/hotaweme/v1/web/search/item/"
    params = {
        "device_platform": "webapp",
        "aid": "6383",
        "channel": "channel_pc_web",
        "search_channel": "aweme_general",
        "sort_type": "0",
        "publish_time": "0",
        "keyword": keyword,
        "search_source": "normal_search",
        "query_correct_type": "1",
        "is_filter_search": "0",
        "from_group_id": "",
        "offset": "0",
        "count": str(count),
        "pc_client_type": "1",
        "version_code": "190700",
        "version_name": "19.7.0",
        "cookie_enabled": "true",
        "screen_width": "1920",
        "screen_height": "1080",
        "browser_language": "zh-CN",
        "browser_platform": "Win32",
        "browser_name": "Chrome",
        "browser_version": "131.0.0.0",
        "browser_online": "true",
        "engine_name": "Blink",
        "engine_version": "131.0.0.0",
        "os_name": "Windows",
        "os_version": "10",
        "cpu_core_num": "16",
        "device_memory": "8",
        "platform": "PC",
        "downlink": "10",
        "effective_type": "4g",
        "round_trip_time": "50",
        "msToken": ms_token,
    }
    url = f"{base_url}?{urlencode(params)}"

    # 调用 SignSrv 获取签名
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            sign_resp = await client.post(
                f"http://127.0.0.1:{settings.SIGN_SRV_PORT}/sign/douyin",
                json={"url": url, "user_agent": ua},
            )
            sign_data = sign_resp.json()
        except Exception:
            return ""

    a_bogus = sign_data.get("a_bogus", "")
    if not a_bogus:
        logger.warning("[douyin-http] a_bogus 为空")
        return ""

    params["a_bogus"] = a_bogus
    full_url = f"{base_url}?{urlencode(params)}"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            full_url,
            headers={
                "User-Agent": ua,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": f"https://www.douyin.com/hotsearch/{quote(keyword)}",
                "Cookie": cookie_str,
                "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not:A-Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
            },
        )
        data = resp.json()

    status_code = data.get("status_code", 0)
    if status_code != 0:
        logger.warning(f"[douyin-http] API 返回 status_code={status_code}: {data.get('status_msg', '')}")
        return ""

    items = []
    for item in data.get("data", []) or []:
        info = item.get("aweme_info", item)
        if not info:
            continue
        author = info.get("author", {}) or {}
        stat = info.get("statistics", {}) or {}
        video = info.get("video", {}) or {}
        items.append({
            "title": info.get("desc", ""),
            "author": author.get("nickname", ""),
            "plays": stat.get("play_count", 0),
            "likes": stat.get("digg_count", 0),
            "aweme_id": str(info.get("aweme_id", "")),
            "sec_uid": author.get("sec_uid", ""),
            "cover_url": (video.get("cover", {}) or {}).get("url_list", [""])[0],
            "link": f"https://www.douyin.com/hotvideo/{info.get('aweme_id', '')}",
        })

    logger.info(f"[douyin-http] SignSrv 直连成功: {len(items)} 条")
    return json.dumps(items, ensure_ascii=False)


async def douyin_search(keyword: str, count: int = 40) -> str:
    """抖音搜索 — 纯 HTTP Session 优先 → SignSrv → CDP 浏览器 fallback。"""
    logger.info(f"抖音搜索: keyword={keyword} count={count}")

    # ── Path 1: 纯 HTTP Session（零浏览器，毫秒级）─────────
    try:
        from src.utils.session_manager import ensure_session
        if await ensure_session("douyin"):
            from src.utils.douyin_http import search_all
            items = await search_all(keyword, limit=count)
            if items:
                logger.info(f"[douyin-session] 纯HTTP直连成功: {len(items)} 条")
                return json.dumps(items, ensure_ascii=False)
    except Exception as exc:
        logger.warning(f"抖音 Session HTTP 失败: {exc}，尝试下一路径")

    # ── Path 2: SignSrv 直连（备选）─────────────────────────
    if settings.SIGN_SRV_ENABLED and "douyin" in settings.SIGN_PLATFORM_ENABLED:
        try:
            result = await _douyin_search_http(keyword, count)
            if result:
                return result
        except Exception as exc:
            logger.warning(f"抖音 SignSrv 直连失败: {exc}，fallback 到浏览器")

    # ── Path 3: CDP 浏览器（最终兜底）──────────────────────
    try:
        page = await browser.new_page()
        try:
            api_items = []
            seen_aweme = set()

            async def on_response(resp):
                if "general/search/single" in resp.url:
                    try:
                        body = await resp.json()
                        data = body.get("data") or []
                        for item in data:
                            info = item.get("aweme_info", item)
                            aid = str(info.get("aweme_id", ""))
                            if not aid or aid in seen_aweme:
                                continue
                            seen_aweme.add(aid)
                            author = info.get("author", {}) or {}
                            stat = info.get("statistics", {}) or {}
                            video = info.get("video", {}) or {}
                            api_items.append({
                                "title": info.get("desc", ""),
                                "author": author.get("nickname", ""),
                                "plays": stat.get("play_count", 0),
                                "likes": stat.get("digg_count", 0),
                                "aweme_id": aid,
                                "sec_uid": author.get("sec_uid", ""),
                                "cover_url": (video.get("cover", {}) or {}).get("url_list", [""])[0],
                                "link": f"https://www.douyin.com/hotvideo/{aid}",
                            })
                    except Exception:
                        pass

            page.on("response", lambda resp: asyncio.ensure_future(on_response(resp)))

            await page.goto(f"https://www.douyin.com/hotsearch/{keyword}", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(5000)

            max_scrolls = max((count // 10) + 3, 6)
            for _ in range(max_scrolls):
                if len(api_items) >= count:
                    break
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2500)

            # 等待最后一批API响应
            await page.wait_for_timeout(3000)

            # DOM 兜底：API 拦截无结果时尝试 DOM 提取
            if not api_items:
                logger.info("抖音搜索: API 拦截无结果，尝试 DOM 兜底")
                try:
                    dom_result = await page.evaluate(_SEARCH_JS)
                    if dom_result:
                        for item in dom_result:
                            if item.get("title"):
                                dom_link = item.get("link", "")
                                api_items.append({
                                    "title": item.get("title", ""),
                                    "author": item.get("author", ""),
                                    "plays": item.get("plays", 0),
                                    "likes": 0,
                                    "aweme_id": dom_link.split("/video/")[-1] if "/video/" in (dom_link or "") else "",
                                    "sec_uid": "",
                                    "cover_url": "",
                                    "link": dom_link,
                                })
                except Exception:
                    pass

            # 检查是否需要登录
            if not api_items:
                try:
                    body_text = await page.evaluate("() => document.body?.textContent?.slice(0, 500) || ''")
                    if "登录" in body_text and "抖音" in body_text:
                        logger.warning("抖音搜索: 可能需要登录，请先手动登录抖音")
                except Exception:
                    pass

            result = api_items[:count]
            logger.info(f"抖音搜索完成: {len(result)} 条")
            return json.dumps(result, ensure_ascii=False)
        finally:
            await page.close()
    except Exception as e:
        logger.warning(f"抖音搜索异常: {e}")
        return json.dumps([], ensure_ascii=False)


async def douyin_hot() -> str:
    """爬取抖音熱榜 — JS拿热搜词 + Python douyin_http 搜索增强。"""
    logger.info("抖音熱榜: 開始爬取")
    try:
        page = await browser.new_page()
        try:
            await page.goto("https://www.douyin.com/hot", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(6000)

            # 宽网拦截: 热搜关键词 + 任何含视频数据的 API 响应
            hot_keywords = []
            hot_videos = []
            video_seen = set()

            async def on_response(resp):
                if "json" not in (resp.headers.get("content-type", "")):
                    return
                try:
                    body = await resp.json()
                except Exception:
                    return
                data = body.get("data", {}) if isinstance(body, dict) else {}

                # 热搜关键词
                if isinstance(data, dict) and ("word_list" in data or "trending_list" in data):
                    for item in data.get("word_list", []):
                        w = item.get("word", "")
                        if w:
                            hot_keywords.append({
                                "title": w, "hot_value": item.get("hot_value", ""),
                                "position": item.get("position", ""),
                                "link": f"https://www.douyin.com/hotsearch/{quote(w)}",
                            })
                    for item in data.get("trending_list", []):
                        w = item.get("word", "")
                        if w:
                            hot_keywords.append({
                                "title": w, "hot_value": item.get("hot_value", ""),
                                "link": f"https://www.douyin.com/hotsearch/{quote(w)}",
                            })

                # 视频数据: 从 aweme_list 或 data list 中提取
                items = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = data.get("aweme_list", []) or data.get("list", []) or data.get("data", [])
                    if not isinstance(items, list):
                        items = []

                for item in items:
                    info = item.get("aweme_info", item)
                    aid = str(info.get("aweme_id", ""))
                    if not aid or aid in video_seen:
                        continue
                    video_seen.add(aid)
                    stats = info.get("statistics", {}) or {}
                    author_info = info.get("author", {}) or {}
                    cover_list = ((info.get("cover", {}) or {}).get("url_list") if isinstance(info.get("cover"), dict) else [])
                    hot_videos.append({
                        "title": info.get("desc", ""),
                        "author": author_info.get("nickname", ""),
                        "plays": str(stats.get("play_count", "")),
                        "likes": str(stats.get("digg_count", "")),
                        "comments": str(stats.get("comment_count", "")),
                        "cover_url": cover_list[0] if cover_list else "",
                        "link": f"https://www.douyin.com/hotvideo/{aid}",
                        "aweme_id": aid,
                    })

            page.on("response", lambda resp: asyncio.ensure_future(on_response(resp)))

            # 等待 API 加载 + 滚动触发更多
            await page.wait_for_timeout(5000)
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)

            # 合并: 视频优先 + 关键词不含视频的
            hot_items = list(hot_videos)
            kw_seen = {v.get("title", "") for v in hot_videos}
            for kw in hot_keywords:
                if kw["title"] not in kw_seen:
                    kw_seen.add(kw["title"])
                    hot_items.append(kw)

            # DOM 兜底
            if not hot_items:
                dom = await page.evaluate("""() => {
    const items = document.querySelectorAll('[class*="hot"] [class*="title"], [class*="trend"] [class*="title"], [class*="HotItem"]');
    const seen = new Set();
    return Array.from(items).filter(el => {
        const t = el.textContent.trim();
        if (!t || t.length < 3 || seen.has(t)) return false;
        seen.add(t);
        return true;
    }).map(el => ({ title: el.textContent.trim(), link: 'https://www.douyin.com/hotsearch/' + encodeURIComponent(el.textContent.trim()) }));
}""")
                hot_items = list(dom) if dom else []

            logger.info(f"抖音熱榜完成: {len(hot_items)} 條 (视频{len(hot_videos)}+关键词{len(hot_keywords)})")
            return json.dumps(hot_items, ensure_ascii=False)
        finally:
            await page.close()
    except Exception as e:
        logger.warning(f"抖音熱榜异常: {e}")
        return json.dumps([], ensure_ascii=False)


async def douyin_detail(video_id: str) -> str:
    """爬取抖音視頻詳情。"""
    logger.info(f"抖音詳情: video_id={video_id}")
    try:
        page = await browser.new_page()
        try:
            await page.goto(f"https://www.douyin.com/hotvideo/{video_id}", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(5000)
            result = await page.evaluate("""() => {
    const titleEl = document.querySelector('[class*="title"], [class*="Title"], h1');
    const descEl = document.querySelector('[class*="desc"], [class*="Desc"]');
    const playEl = document.querySelector('[class*="play"], [class*="Play"], [class*="count"]');
    const likeEl = document.querySelector('[class*="like"]:not([class*="digg"])');
    return {
        title: titleEl?.textContent?.trim() || '',
        desc: descEl?.textContent?.trim() || '',
        plays: playEl?.textContent?.trim() || '',
        likes: likeEl?.textContent?.trim() || '',
    };
}""")
            logger.info("抖音詳情完成")
            return json.dumps(result, ensure_ascii=False)
        finally:
            await page.close()
    except Exception as e:
        logger.warning(f"抖音詳情异常: {e}")
        return json.dumps({}, ensure_ascii=False)


async def douyin_comment(video_id: str, count: int = 50) -> str:
    """抖音视频评论 — 拦截 + 主动翻页 comment API。"""
    logger.info(f"抖音評論: video_id={video_id} count={count}")
    try:
        page = await browser.new_page()
        try:
            comments = []
            seen_cids = set()

            async def on_response(resp):
                if "comment/list" in resp.url:
                    try:
                        body = await resp.json()
                        for c in (body.get("comments") or []):
                            cid = str(c.get("cid", ""))
                            if not cid or cid in seen_cids:
                                continue
                            seen_cids.add(cid)
                            user = c.get("user", {}) or {}
                            comments.append({
                                "user": user.get("nickname", ""),
                                "content": c.get("text", ""),
                                "likes": c.get("digg_count", 0),
                                "reply_count": c.get("reply_comment_total", 0),
                            })
                    except Exception:
                        pass

            page.on("response", lambda resp: asyncio.ensure_future(on_response(resp)))

            await page.goto(f"https://www.douyin.com/hotvideo/{video_id}", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(5000)

            # 滚动触发首頁评论加载
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.3)")
            await page.wait_for_timeout(3000)

            # 主动翻页获取更多评论
            max_pages = max((count // 20) + 3, 5)
            for page_num in range(max_pages):
                if len(comments) >= count:
                    break
                cursor = page_num * 20
                try:
                    more = await page.evaluate(f"""async () => {{
                        const resp = await fetch("https://www.douyin.com/hotaweme/v1/web/comment/list/?device_platform=webapp&aid=6383&channel=channel_pc_web&aweme_id={video_id}&cursor={cursor}&count=20");
                        const data = await resp.json();
                        return (data.comments || []).map(c => ({{
                            user: (c.user || {{}}).nickname || '',
                            content: c.text || '',
                            likes: c.digg_count || 0,
                            cid: String(c.cid || ''),
                        }}));
                    }}""")
                    new_count = 0
                    for c in (more or []):
                        cid = c.get("cid", "")
                        if cid and cid not in seen_cids:
                            seen_cids.add(cid)
                            comments.append({
                                "user": c.get("user", ""),
                                "content": c.get("content", ""),
                                "likes": c.get("likes", 0),
                            })
                            new_count += 1
                    if new_count == 0:
                        break
                except Exception:
                    break

                await page.wait_for_timeout(1000)

            result = comments[:count]
            logger.info(f"抖音評論完成: {len(result)} 條")
            return json.dumps(result, ensure_ascii=False)
        finally:
            await page.close()
    except Exception as e:
        logger.warning(f"抖音評論异常: {e}")
        return json.dumps([], ensure_ascii=False)


async def douyin_user_videos(user_id: str) -> str:
    """抖音用户视频 — CDP DOM 抓取."""
    logger.info(f"抖音用戶視頻: user_id={user_id}")
    try:
        page = await browser.new_page()
        try:
            await page.goto(f"https://www.douyin.com/hotuser/{user_id}", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(5000)
            for _ in range(2):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1500)
            result = await page.evaluate(_USER_JS)
            logger.info(f"抖音用戶視頻完成: {len(result)} 條結果")
            return json.dumps(result, ensure_ascii=False)
        finally:
            await page.close()
    except Exception as e:
        logger.warning(f"抖音用戶視頻异常: {e}")
        return json.dumps([], ensure_ascii=False)


class DouyinAdapter(PlatformAdapter):
    @property
    def name(self) -> str:
        return "douyin"

    @property
    def need_login(self) -> bool:
        return True

    async def search(self, keyword: str, limit: Optional[int] = None,
                     sort_type: int = 0, publish_time: int = 0,
                     search_channel: str = "") -> list[dict]:
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
