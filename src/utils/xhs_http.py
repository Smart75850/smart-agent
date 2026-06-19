"""小红书纯 HTTP 搜索客户端 — 零浏览器依赖。

从 CDP Chrome 一次性收割 x-s + x-s-common + cookies，
之后直接发 HTTP POST 请求到搜索 API，x-s 可跨请求复用。
"""
import asyncio, json, random, string, logging
from pathlib import Path
from datetime import datetime

import httpx

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
logger = logging.getLogger(__name__)

SEARCH_URL = "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes"
SESSION_FILE = Path(__file__).resolve().parent.parent.parent / "browser_data/xhs_http_session.json"


class XhsSession:
    __slots__ = ("cookies_str", "xs_common", "xs", "xt", "xb3", "xxray", "harvested_at")

    def __init__(self):
        self.cookies_str = ""
        self.xs_common = ""
        self.xs = ""
        self.xt = ""
        self.xb3 = ""
        self.xxray = ""
        self.harvested_at = ""

    def is_valid(self) -> bool:
        return bool(self.cookies_str)  # cookies_str 够用，xs 由 xhshow 动态生成

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__slots__}

    @classmethod
    def from_dict(cls, d: dict) -> "XhsSession":
        s = cls()
        for k in cls.__slots__:
            setattr(s, k, d.get(k, ""))
        return s


def _load_session() -> XhsSession:
    if SESSION_FILE.exists():
        try:
            return XhsSession.from_dict(json.loads(SESSION_FILE.read_text("utf-8")))
        except (json.JSONDecodeError, KeyError):
            pass
    return XhsSession()


def _save_session(sess: XhsSession):
    sess.harvested_at = datetime.now().isoformat()
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(sess.to_dict(), ensure_ascii=False, indent=2), "utf-8")


async def harvest_persistent() -> XhsSession:
    """使用持久化 Playwright Profile 收割 XHS 会话——对标 MediaCrawler。

    Profile 保存在 browser_data/xhs_profile/，一次登录永久有效。
    """
    import os
    os.environ["no_proxy"] = "127.0.0.1,localhost"
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    from playwright.async_api import async_playwright

    profile_dir = str(_PROJECT_ROOT / "browser_data" / "xhs_profile")
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            profile_dir,
            headless=False,
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # 检查真正登录状态（有 a1 cookie 且未过期）
        cookies = await context.cookies()
        has_a1 = any(c['name'] == 'a1' for c in cookies)
        need_login = "login" in page.url or not has_a1

        if need_login:
            logger.warning("XHS 未登录或 a1 过期，请在弹出窗口中扫码登录...")
            # 强制打开登录页
            await page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            # 尝试点击登录按钮
            try:
                login_btn = await page.query_selector('text=登录')
                if login_btn:
                    await login_btn.click()
                    await page.wait_for_timeout(2000)
            except Exception:
                pass
            for i in range(90):
                await asyncio.sleep(2)
                cookies = await context.cookies()
                has_a1 = any(c['name'] == 'a1' for c in cookies)
                if has_a1 and "login" not in page.url:
                    logger.info("XHS 登录成功")
                    break
                if i % 15 == 0:
                    logger.info(f"  等待登录... ({i*2}s)")
            else:
                logger.warning("XHS 登录超时")

        # 收割 cookies
        cookies = await context.cookies()
        xhs_cookies = [c for c in cookies if "xiaohongshu" in c.get("domain", "")]
        cookies_str = "; ".join(f"{c['name']}={c['value']}" for c in xhs_cookies)

        sess = XhsSession()
        sess.cookies_str = cookies_str
        sess.harvested_at = datetime.now().isoformat()
        if sess.is_valid():
            _save_session(sess)
        await context.close()
        return sess


async def harvest_from_cdp(port: int = 9222) -> XhsSession:
    """从 CDP Chrome 收割 XHS 会话上下文。"""
    import os
    os.environ["no_proxy"] = "127.0.0.1,localhost"
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()

        # 导航到小红书触发 API
        await page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # 执行搜索触发签名生成
        captured = {"xs": "", "xs_common": "", "xt": "", "xb3": "", "xxray": ""}

        async def on_request(req):
            if "search/notes" in req.url and not captured["xs"]:
                h = req.headers
                captured["xs"] = h.get("x-s", "")
                captured["xs_common"] = h.get("x-s-common", "")
                captured["xt"] = h.get("x-t", "")
                captured["xb3"] = h.get("x-b3-traceid", "")
                captured["xxray"] = h.get("x-xray-traceid", "")

        page.on("request", on_request)
        await page.goto("https://www.xiaohongshu.com/search_result?keyword=test", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(4000)

        # Cookies
        all_cookies = await context.cookies()
        xhs_cookies = [c for c in all_cookies if "xiaohongshu" in c.get("domain", "")]
        cookies_str = "; ".join(f"{c['name']}={c['value']}" for c in xhs_cookies)

        await browser.close()

    sess = XhsSession()
    sess.cookies_str = cookies_str
    sess.xs_common = captured["xs_common"]
    sess.xs = captured["xs"]
    sess.xt = captured["xt"]
    sess.xb3 = captured["xb3"]
    sess.xxray = captured["xxray"]

    if sess.is_valid():
        _save_session(sess)

    return sess


def _build_headers(sess: XhsSession, method: str = "POST", uri: str = "",
                   payload: dict | None = None) -> dict:
    base = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "cookie": sess.cookies_str,
        "origin": "https://www.xiaohongshu.com",
        "referer": "https://www.xiaohongshu.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }
    # 尝试 xhshow 生成新鲜签名
    if sess.cookies_str:
        try:
            from src.utils.xhs_sign import generate_xs_headers
            fresh = generate_xs_headers(method, uri, sess.cookies_str, payload=payload)
            if fresh and fresh.get("x-s"):
                base.update(fresh)
                return base
        except ImportError:
            pass  # signing not available in public version
    # 回退到 CDP 收割的旧签名
    base.update({
        "x-s-common": sess.xs_common,
        "x-s": sess.xs,
        "x-t": sess.xt,
        "x-b3-traceid": sess.xb3 or ''.join(random.choices(string.hexdigits.lower(), k=16)),
        "x-xray-traceid": sess.xxray or ''.join(random.choices(string.hexdigits.lower(), k=32)),
    })
    return base


def _parse_items(data: dict) -> list[dict]:
    items = data.get("data", {}).get("items", []) if isinstance(data.get("data"), dict) else []
    results = []
    for item in items:
        nc = item.get("note_card", item)
        interact = nc.get("interact_info", {}) or {}
        cover_info = nc.get("cover", {}) or {}
        author_info = nc.get("user", {}) or {}
        note_id = item.get("id", "")
        image_list = nc.get("image_list", []) or []
        results.append({
            # 基础信息
            "title": nc.get("display_title", ""),
            "note_id": note_id,
            "note_type": nc.get("type", ""),  # normal=图文, video=视频
            "cover_url": cover_info.get("url_default", "") or cover_info.get("url", ""),
            "cover_width": cover_info.get("width", 0),
            "cover_height": cover_info.get("height", 0),
            "images": [img.get("url_default", img.get("url", "")) for img in image_list],
            # 作者信息
            "author": author_info.get("nickname", ""),
            "author_id": author_info.get("user_id", ""),
            "author_avatar": author_info.get("avatar", ""),
            # 互动数据
            "likes": interact.get("liked_count", 0),
            "collects": interact.get("collected_count", 0),
            "comments": interact.get("comment_count", 0),
            "shares": interact.get("shared_count", 0),
            "liked": interact.get("liked", False),
            "collected": interact.get("collected", False),
            # 角标 & 链接
            "corner_tag": (nc.get("corner_tag_info", []) or [{}])[0].get("text", "") if nc.get("corner_tag_info") else "",
            "tags": [t.get("name", "") for t in (nc.get("tag_list", []) or []) if t.get("name")],
            "link": f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else "",
        })
    return results


async def search(keyword: str, count: int = 20, page: int = 1) -> list[dict]:
    """小紅書搜索 — 經 CDP Chrome 發請求（真實 TLS，避免封號）。

    同抖音一樣，用 Playwright 連接已登入嘅 CDP Chrome，
    截取 API 響應直接提取數據。唔再用 httpx + 收割 token，
    因為 httpx 嘅 TLS 指紋會被小紅書檢測，導致封號。
    """
    from playwright.async_api import async_playwright
    import os
    os.environ["no_proxy"] = "127.0.0.1,localhost"
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"

    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # Navigate to search + wait for JS to load
        search_url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}"
        await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(8000)  # 等 JavaScript 完全加載

        # Intercept search API responses (v1/search/notes is the main search endpoint)
        api_data = []

        async def on_response(response):
            if "v1/search/notes" in response.url and response.status == 200:
                try:
                    body = await response.json()
                    if body.get("success") or body.get("code") == 0:
                        if body.get("data", {}).get("items"):
                            api_data.append(body)
                except Exception:
                    pass

        page.on("response", on_response)

        # Scroll多次觸發 API 加載
        for _ in range(3):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)

        await page.close()
        await playwright.stop()

        if api_data:
            return _parse_items(api_data[0])

        logger.warning("XHS CDP: no search API response captured")
        return []

    except Exception as e:
        logger.error(f"XHS CDP search failed: {e}")
        return []


async def search_all(keyword: str, limit: int = 40) -> list[dict]:
    """分頁搜索 + 隨機延遲（防止頻率檢測封號）。"""
    all_results = []
    seen_ids = set()
    page = 1
    while len(all_results) < limit:
        items = await search(keyword, count=20, page=page)
        if not items:
            break
        new_items = [i for i in items if i["note_id"] not in seen_ids]
        for item in new_items:
            seen_ids.add(item["note_id"])
        all_results.extend(new_items)
        page += 1
        if len(new_items) < 5:
            break
        # 🆕 隨機延遲 2-5 秒，模擬人類瀏覽行為，防封號
        import asyncio as _asyncio
        delay = 2.0 + _asyncio.get_event_loop().time() % 3.0  # 2-5s random-ish
        await _asyncio.sleep(delay)
    return all_results[:limit]
