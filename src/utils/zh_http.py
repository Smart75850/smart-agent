"""知乎纯 HTTP 搜索 — 零浏览器，仅需 cookies。"""
import json, logging
from pathlib import Path
from datetime import datetime
from urllib.parse import quote
import httpx

logger = logging.getLogger(__name__)
SEARCH_URL = "https://www.zhihu.com/api/v4/search_v3"
SESSION_FILE = Path(__file__).resolve().parent.parent.parent / "browser_data/zh_http_session.json"


class ZhSession:
    __slots__ = ("cookies_str", "harvested_at")
    def __init__(self): self.cookies_str = ""; self.harvested_at = ""
    def is_valid(self) -> bool: return bool(self.cookies_str)
    def to_dict(self) -> dict: return {"cookies_str": self.cookies_str, "harvested_at": self.harvested_at}
    @classmethod
    def from_dict(cls, d: dict) -> "ZhSession":
        s = cls(); s.cookies_str = d.get("cookies_str", ""); s.harvested_at = d.get("harvested_at", ""); return s


def _load() -> ZhSession:
    if SESSION_FILE.exists():
        try: return ZhSession.from_dict(json.loads(SESSION_FILE.read_text("utf-8")))
        except: pass
    return ZhSession()

def _save(s: ZhSession):
    s.harvested_at = datetime.now().isoformat()
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(s.to_dict(), ensure_ascii=False, indent=2), "utf-8")

async def harvest_from_cdp(port: int = 9222) -> ZhSession:
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
        cookies_str = "; ".join(f"{c['name']}={c['value']}" for c in zh_cookies)
        await browser.close()
    sess = ZhSession(); sess.cookies_str = cookies_str
    if sess.is_valid(): _save(sess)
    return sess

async def search(keyword: str, count: int = 20, offset: int = 0) -> list[dict]:
    sess = _load()
    if not sess.is_valid(): return []
    params = {"gk_version": "gz-gaokao", "t": "general", "q": keyword, "correction": "1", "offset": str(offset), "limit": str(min(count, 20)), "lc_idx": "0", "show_all_topics": "0", "search_source": "Normal"}
    headers = {"accept": "application/json", "cookie": sess.cookies_str, "referer": f"https://www.zhihu.com/search?type=content&q={quote(keyword)}", "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36", "x-api-version": "3.0.91"}
    from src.utils.http_client import create_httpx_client
    async with create_httpx_client(15) as client:
        resp = await client.get(SEARCH_URL, params=params, headers=headers)
        data = resp.json()
    results = []
    for item in data.get("data", []):
        obj = item.get("object", {}) or {}
        if item.get("type") != "search_result": continue
        q = obj.get("question", {}) or {}
        url = obj.get("url", "")
        if url:
            url = url.replace("api.zhihu.com", "www.zhihu.com")
            if not url.startswith("https://"):
                url = "https://www.zhihu.com" + (url if url.startswith("/") else "/" + url)
        results.append({"title": obj.get("title", "") or q.get("name", ""), "excerpt": obj.get("excerpt", ""), "url": url, "votes": obj.get("voteup_count", 0) or 0, "comments": obj.get("comment_count", 0) or 0, "question_id": str(obj.get("id", "")), "author": (obj.get("author", {}) or {}).get("name", ""),})
    return results

async def search_all(keyword: str, limit: int = 40) -> list[dict]:
    all_results, seen, offset = [], set(), 0
    while len(all_results) < limit:
        items = await search(keyword, count=20, offset=offset)
        if not items: break
        new = [i for i in items if i["question_id"] not in seen]
        for i in new: seen.add(i["question_id"])
        all_results.extend(new)
        offset += 20
    return all_results[:limit]
