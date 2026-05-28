"""快手纯 HTTP 搜索客户端 — 零浏览器，仅需 cookies。"""
import json, random, string, logging
from pathlib import Path
from datetime import datetime
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.kuaishou.com/rest/v/search/feed"
SESSION_FILE = Path(__file__).resolve().parent.parent.parent / "browser_data/ks_http_session.json"


class KsSession:
    __slots__ = ("cookies_str", "harvested_at")

    def __init__(self):
        self.cookies_str = ""
        self.harvested_at = ""

    def is_valid(self) -> bool:
        return bool(self.cookies_str)

    def to_dict(self) -> dict:
        return {"cookies_str": self.cookies_str, "harvested_at": self.harvested_at}

    @classmethod
    def from_dict(cls, d: dict) -> "KsSession":
        s = cls()
        s.cookies_str = d.get("cookies_str", "")
        s.harvested_at = d.get("harvested_at", "")
        return s


def _load_session() -> KsSession:
    if SESSION_FILE.exists():
        try:
            return KsSession.from_dict(json.loads(SESSION_FILE.read_text("utf-8")))
        except (json.JSONDecodeError, KeyError):
            pass
    return KsSession()


def _save_session(sess: KsSession):
    sess.harvested_at = datetime.now().isoformat()
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(sess.to_dict(), ensure_ascii=False, indent=2), "utf-8")


async def harvest_from_cdp(port: int = 9222) -> KsSession:
    """从 CDP Chrome 收割快手 cookies。"""
    import os
    os.environ["no_proxy"] = "127.0.0.1,localhost"
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()

        await page.goto("https://www.kuaishou.com", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)

        all_cookies = await context.cookies()
        ks_cookies = [c for c in all_cookies if "kuaishou" in c.get("domain", "")]
        cookies_str = "; ".join(f"{c['name']}={c['value']}" for c in ks_cookies)

        await browser.close()

    sess = KsSession()
    sess.cookies_str = cookies_str
    if sess.is_valid():
        _save_session(sess)
    return sess


async def search(keyword: str, count: int = 20, pcursor: str = "") -> tuple[list[dict], str]:
    """返回 (results, next_pcursor)。pcursor 为空表示第一页。"""
    sess = _load_session()
    if not sess.is_valid():
        logger.warning("快手会话无效，请先收割")
        return [], ""

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "cookie": sess.cookies_str,
        "referer": f"https://www.kuaishou.com/search/video?keyword={quote(keyword)}",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    }

    body = {
        "keyword": keyword,
        "pcursor": pcursor,
        "page": 1,
        "searchSessionId": ''.join(random.choices('0123456789abcdef', k=32)),
    }

    from src.utils.http_client import create_httpx_client
    async with create_httpx_client(15) as client:
        resp = await client.post(SEARCH_URL, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()

    feeds = data.get("feeds", [])
    next_pcursor = data.get("pcursor", "")

    results = []
    for f in feeds:
        photo = f.get("photo", {}) or {}
        author = f.get("user", {}) or {}
        pid = photo.get("id", "")
        results.append({
            "title": photo.get("caption", ""),
            "author": author.get("name", ""),
            "likes": photo.get("likeCount", 0) or 0,
            "plays": photo.get("viewCount", 0) or 0,
            "photo_id": pid,
            "duration": photo.get("duration", 0),
            "cover_url": (photo.get("coverUrls", []) or [{}])[0].get("url", ""),
            "link": f"https://www.kuaishou.com/short-video/{pid}" if pid else "",
        })

    return results, str(next_pcursor) if next_pcursor else ""


async def search_all(keyword: str, limit: int = 40) -> list[dict]:
    all_results = []
    seen_ids = set()
    pcursor = ""
    while len(all_results) < limit:
        items, pcursor = await search(keyword, count=20, pcursor=pcursor)
        if not items:
            break
        new_items = [i for i in items if i["photo_id"] not in seen_ids]
        for item in new_items:
            seen_ids.add(item["photo_id"])
        all_results.extend(new_items)
        if not pcursor or pcursor == "no_more":
            break
    return all_results[:limit]
