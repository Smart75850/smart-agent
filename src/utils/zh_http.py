"""知乎纯 HTTP 搜索 — curl_cffi TLS 指纹 + 持久化会话。

支持两种收割方式:
  1. harvest_from_cdp — 从 CDP Chrome 收割 cookies
  2. harvest_persistent — Playwright persistent context，一次登录长期有效
"""
import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime
from urllib.parse import quote

from curl_cffi import requests as cffi_requests

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.zhihu.com/api/v4/search_v3"
SESSION_FILE = _PROJECT_ROOT / "browser_data/zh_http_session.json"

# curl_cffi TLS 指纹伪装
_IMPERSONATE = "chrome124"

_cffi_session: "cffi_requests.Session | None" = None


def _get_http_session() -> cffi_requests.Session:
    global _cffi_session
    if _cffi_session is None:
        _cffi_session = cffi_requests.Session()
        _cffi_session.timeout = 15
        try:
            from src.utils.http_client import create_curl_cffi_proxy
            proxy = create_curl_cffi_proxy()
            if proxy:
                _cffi_session.proxies = proxy
        except Exception:
            pass
    return _cffi_session


class ZhSession:
    __slots__ = ("cookies_str", "harvested_at")

    def __init__(self):
        self.cookies_str = ""
        self.harvested_at = ""

    def is_valid(self) -> bool:
        return bool(self.cookies_str)

    def to_dict(self) -> dict:
        return {"cookies_str": self.cookies_str, "harvested_at": self.harvested_at}

    @classmethod
    def from_dict(cls, d: dict) -> "ZhSession":
        s = cls()
        s.cookies_str = d.get("cookies_str", "")
        s.harvested_at = d.get("harvested_at", "")
        return s


def _load() -> ZhSession:
    if SESSION_FILE.exists():
        try:
            return ZhSession.from_dict(json.loads(SESSION_FILE.read_text("utf-8")))
        except (json.JSONDecodeError, KeyError):
            pass
    return ZhSession()


def _save(s: ZhSession):
    s.harvested_at = datetime.now().isoformat()
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(s.to_dict(), ensure_ascii=False, indent=2), "utf-8")


# ── 收割函数 ────────────────────────────────────────────────

async def harvest_persistent() -> ZhSession:
    """使用持久化 Playwright Profile 收割知乎会话。

    Profile 保存在 browser_data/zh_profile/，一次登录长期有效。
    如果未登录，弹出浏览器窗口让用户扫码。
    """
    import os
    os.environ["no_proxy"] = "127.0.0.1,localhost"
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    from playwright.async_api import async_playwright

    profile_dir = str(_PROJECT_ROOT / "browser_data" / "zh_profile")
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
        await page.goto("https://www.zhihu.com", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # 检查登录状态（有 z_c0 或 login 不在 URL）
        cookies = await context.cookies()
        has_zc0 = any(c['name'] == 'z_c0' for c in cookies)
        need_login = "login" in page.url or (not has_zc0 and "signin" in page.url)

        if need_login:
            logger.warning("知乎未登录，请在弹出窗口中扫码登录...")
            await page.goto("https://www.zhihu.com/signin", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            for i in range(90):
                await asyncio.sleep(2)
                cookies = await context.cookies()
                has_zc0 = any(c['name'] == 'z_c0' for c in cookies)
                current_url = page.url
                if has_zc0 and "signin" not in current_url:
                    logger.info("知乎登录成功")
                    break
                if i % 15 == 0:
                    logger.info(f"  等待登录... ({i*2}s)")
            else:
                logger.warning("知乎登录超时，使用当前 cookies 继续")

        # 收割所有知乎相关 cookies
        cookies = await context.cookies()
        zh_cookies = [c for c in cookies if "zhihu" in c.get("domain", "")]
        # 如果按 domain 筛选后太少，就把所有 cookies 都包括
        if len(zh_cookies) < 3:
            zh_cookies = cookies
        cookies_str = "; ".join(f"{c['name']}={c['value']}" for c in zh_cookies)

        await context.close()

    sess = ZhSession()
    sess.cookies_str = cookies_str
    if sess.is_valid():
        _save(sess)
        cookie_names = [c['name'] for c in zh_cookies]
        logger.info(f"知乎会话收割成功: {len(zh_cookies)} 个 cookies, 含 {cookie_names[:5]}...")
    return sess


async def harvest_from_cdp(port: int = 9222) -> ZhSession:
    """从 CDP Chrome 收割知乎 cookies。"""
    import os
    os.environ["no_proxy"] = "127.0.0.1,localhost"
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.zhihu.com", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)
        all_cookies = await context.cookies()
        zh_cookies = [c for c in all_cookies if "zhihu" in c.get("domain", "")]
        if len(zh_cookies) < 3:
            zh_cookies = all_cookies
        cookies_str = "; ".join(f"{c['name']}={c['value']}" for c in zh_cookies)
        await browser.close()
    sess = ZhSession()
    sess.cookies_str = cookies_str
    if sess.is_valid():
        _save(sess)
    return sess


# ── 核心搜索 ────────────────────────────────────────────────

async def search(keyword: str, count: int = 20, offset: int = 0) -> list[dict]:
    """纯 HTTP 知乎搜索（curl_cffi TLS 指纹）。"""
    sess = _load()
    if not sess.is_valid():
        logger.warning("知乎会话无效，请先运行 harvest_persistent() 或打开 CDP Chrome")
        return []

    params = {
        "gk_version": "gz-gaokao",
        "t": "general",
        "q": keyword,
        "correction": "1",
        "offset": str(offset),
        "limit": str(min(count, 20)),
        "lc_idx": "0",
        "show_all_topics": "0",
        "search_source": "Normal",
    }
    headers = {
        "accept": "application/json",
        "cookie": sess.cookies_str,
        "referer": f"https://www.zhihu.com/search?type=content&q={quote(keyword)}",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "x-api-version": "3.0.91",
    }

    try:
        http = _get_http_session()
        resp = http.get(
            SEARCH_URL,
            params=params,
            headers=headers,
            impersonate=_IMPERSONATE,
        )
        data = resp.json()
    except Exception as exc:
        logger.error(f"知乎 HTTP 搜索失败: {exc}")
        return []

    results = []
    for item in data.get("data", []):
        obj = item.get("object", {}) or {}
        if item.get("type") != "search_result":
            continue
        q = obj.get("question", {}) or {}
        url = obj.get("url", "")
        if url:
            url = url.replace("api.zhihu.com", "www.zhihu.com")
            if not url.startswith("https://"):
                url = "https://www.zhihu.com" + (url if url.startswith("/") else "/" + url)
        results.append({
            "title": obj.get("title", "") or q.get("name", ""),
            "excerpt": obj.get("excerpt", ""),
            "url": url,
            "votes": obj.get("voteup_count", 0) or 0,
            "comments": obj.get("comment_count", 0) or 0,
            "question_id": str(obj.get("id", "")),
            "author": (obj.get("author", {}) or {}).get("name", ""),
        })
    return results


async def search_all(keyword: str, limit: int = 40) -> list[dict]:
    """分页获取搜索结果直到达到 limit。"""
    all_results, seen, offset = [], set(), 0
    while len(all_results) < limit:
        items = await search(keyword, count=20, offset=offset)
        if not items:
            break
        new = [i for i in items if i["question_id"] not in seen]
        for i in new:
            seen.add(i["question_id"])
        all_results.extend(new)
        offset += 20
    return all_results[:limit]
