"""微博纯 HTTP 搜索 — 零浏览器，仅需 cookies。"""
import json, logging
from pathlib import Path
from datetime import datetime
from urllib.parse import quote
import httpx

logger = logging.getLogger(__name__)
SEARCH_URL = "https://weibo.com/ajax/statuses/search"
SESSION_FILE = Path(__file__).resolve().parent.parent.parent / "browser_data/weibo_http_session.json"


class WeiboSession:
    __slots__ = ("cookies_str", "xsrf_token", "harvested_at")
    def __init__(self): self.cookies_str = ""; self.xsrf_token = ""; self.harvested_at = ""
    def is_valid(self) -> bool: return bool(self.cookies_str)
    def to_dict(self) -> dict: return {"cookies_str": self.cookies_str, "xsrf_token": self.xsrf_token, "harvested_at": self.harvested_at}
    @classmethod
    def from_dict(cls, d: dict) -> "WeiboSession":
        s = cls(); s.cookies_str = d.get("cookies_str", ""); s.xsrf_token = d.get("xsrf_token", ""); s.harvested_at = d.get("harvested_at", ""); return s


def _load() -> WeiboSession:
    if SESSION_FILE.exists():
        try: return WeiboSession.from_dict(json.loads(SESSION_FILE.read_text("utf-8")))
        except: pass
    return WeiboSession()

def _save(s: WeiboSession):
    s.harvested_at = datetime.now().isoformat()
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(s.to_dict(), ensure_ascii=False, indent=2), "utf-8")

async def harvest_from_cdp(port: int = 9222) -> WeiboSession:
    import os
    os.environ["no_proxy"] = "127.0.0.1,localhost"
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://weibo.com", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)
        all_cookies = await context.cookies()
        weibo_cookies = [c for c in all_cookies if "weibo" in c.get("domain", "") or "sina" in c.get("domain", "")]
        cookies_str = "; ".join(f"{c['name']}={c['value']}" for c in weibo_cookies)
        xsrf = ""
        for c in weibo_cookies:
            if c["name"] == "XSRF-TOKEN":
                xsrf = c["value"]
                break
        await browser.close()
    sess = WeiboSession(); sess.cookies_str = cookies_str; sess.xsrf_token = xsrf
    if sess.is_valid(): _save(sess)
    return sess

async def search(keyword: str, count: int = 20, page: int = 1) -> list[dict]:
    sess = _load()
    if not sess.is_valid(): return []
    headers = {
        "accept": "application/json, text/plain, */*",
        "cookie": sess.cookies_str,
        "referer": "https://s.weibo.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "x-requested-with": "XMLHttpRequest",
        "x-xsrf-token": sess.xsrf_token,
        "client-version": "3.0.0",
        "server-version": "v2026.05.25.1",
    }
    params = {"q": keyword, "page": str(page), "count": str(min(count, 20))}
    from src.utils.http_client import create_httpx_client
    async with create_httpx_client(15) as client:
        resp = await client.get(SEARCH_URL, params=params, headers=headers)
        data = resp.json()
    results = []
    for item in data.get("statuses", []) or []:
        user = (item.get("user") or {})
        results.append({
            "mid": item.get("mid", ""),
            "title": (item.get("text_raw", "") or item.get("text", ""))[:200],
            "author": user.get("screen_name", ""),
            "plays": item.get("reads_count", 0) or 0,
            "created_at": item.get("created_at", ""),
            "reposts": item.get("reposts_count", 0),
            "comments": item.get("comments_count", 0),
            "likes": item.get("attitudes_count", 0),
            "url": f"https://weibo.com/{user.get('id', '')}/{item.get('mid', '')}",
        })
    return results

async def search_all(keyword: str, limit: int = 40) -> list[dict]:
    all_results, seen, page = [], set(), 1
    while len(all_results) < limit:
        items = await search(keyword, count=20, page=page)
        if not items: break
        new = [i for i in items if i["mid"] not in seen]
        for i in new: seen.add(i["mid"])
        all_results.extend(new)
        page += 1
    return all_results[:limit]
