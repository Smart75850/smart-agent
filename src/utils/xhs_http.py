"""小红书纯 HTTP 搜索客户端 — 零浏览器依赖。

从 CDP Chrome 一次性收割 x-s + x-s-common + cookies，
之后直接发 HTTP POST 请求到搜索 API，x-s 可跨请求复用。
"""
import json, random, string, logging
from pathlib import Path
from datetime import datetime

import httpx

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
        return bool(self.cookies_str and self.xs_common and self.xs)

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


def _build_headers(sess: XhsSession) -> dict:
    return {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "cookie": sess.cookies_str,
        "origin": "https://www.xiaohongshu.com",
        "referer": "https://www.xiaohongshu.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "x-s-common": sess.xs_common,
        "x-s": sess.xs,
        "x-t": sess.xt,
        "x-b3-traceid": sess.xb3 or ''.join(random.choices(string.hexdigits.lower(), k=16)),
        "x-xray-traceid": sess.xxray or ''.join(random.choices(string.hexdigits.lower(), k=32)),
    }


def _parse_items(data: dict) -> list[dict]:
    items = data.get("data", {}).get("items", []) if isinstance(data.get("data"), dict) else []
    results = []
    for item in items:
        nc = item.get("note_card", item)
        interact = nc.get("interact_info", {}) or {}
        cover_info = nc.get("cover", {}) or {}
        author_info = nc.get("user", {}) or {}
        results.append({
            "title": nc.get("display_title", ""),
            "author": author_info.get("nickname", ""),
            "likes": interact.get("liked_count", 0) or 0,
            "comments": interact.get("comment_count", 0) or 0,
            "note_id": item.get("id", ""),
            "cover_url": cover_info.get("url_default", "") or cover_info.get("url", ""),
            "note_type": nc.get("type", ""),
        })
    return results


async def search(keyword: str, count: int = 20, page: int = 1) -> list[dict]:
    sess = _load_session()
    if not sess.is_valid():
        logger.warning("XHS 会话无效，请先运行收割脚本")
        return []

    headers = _build_headers(sess)
    body = {
        "keyword": keyword,
        "page": page,
        "page_size": min(count, 20),
        "search_id": ''.join(random.choices(string.hexdigits.lower(), k=32)),
        "sort": "general",
        "source": "web_search_result",
        "note_type": 0,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(SEARCH_URL, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()

    code = data.get("code", -1)
    if code != 0:
        logger.warning(f"XHS 搜索失败: code={code}, msg={data.get('msg', '')}")
        return []

    return _parse_items(data)


async def search_all(keyword: str, limit: int = 40) -> list[dict]:
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
    return all_results[:limit]
