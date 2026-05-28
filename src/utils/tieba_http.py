"""贴吧纯 HTTP 搜索 — 使用 curl_cffi 模拟 Chrome TLS 指纹。"""
import hashlib, json, logging, asyncio
from pathlib import Path
from datetime import datetime
from urllib.parse import quote as urlquote
from curl_cffi import requests as curl_requests

PC_SIGN_SECRET = "36770b1f34c9bbf2e7d1a99d2b82fa9e"

def _tieba_sign(params: dict) -> str:
    """贴吧 PC API MD5 签名。"""
    parts = []
    for k in sorted(params.keys()):
        if k in ("sign", "sig"):
            continue
        v = params[k]
        if v is None:
            continue
        parts.append(f"{k}={v}")
    return hashlib.md5(("".join(parts) + PC_SIGN_SECRET).encode()).hexdigest()

logger = logging.getLogger(__name__)
SEARCH_URL = "https://tieba.baidu.com/mo/q/search/multsearch"
SESSION_FILE = Path(__file__).resolve().parent.parent.parent / "browser_data/tieba_http_session.json"


class TiebaSession:
    __slots__ = ("cookies_str", "harvested_at")
    def __init__(self): self.cookies_str = ""; self.harvested_at = ""
    def is_valid(self) -> bool: return bool(self.cookies_str)
    def to_dict(self) -> dict: return {"cookies_str": self.cookies_str, "harvested_at": self.harvested_at}
    @classmethod
    def from_dict(cls, d: dict) -> "TiebaSession":
        s = cls(); s.cookies_str = d.get("cookies_str", ""); s.harvested_at = d.get("harvested_at", ""); return s


def _load() -> TiebaSession:
    if SESSION_FILE.exists():
        try: return TiebaSession.from_dict(json.loads(SESSION_FILE.read_text("utf-8")))
        except: pass
    return TiebaSession()

def _save(s: TiebaSession):
    s.harvested_at = datetime.now().isoformat()
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(s.to_dict(), ensure_ascii=False, indent=2), "utf-8")

async def harvest_from_cdp(port: int = 9222) -> TiebaSession:
    import os
    os.environ["no_proxy"] = "127.0.0.1,localhost"
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://tieba.baidu.com", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)
        all_cookies = await context.cookies()
        tieba_cookies = [c for c in all_cookies if "tieba" in c.get("domain", "") or "baidu" in c.get("domain", "")]
        cookies_str = "; ".join(f"{c['name']}={c['value']}" for c in tieba_cookies)
        await browser.close()
    sess = TiebaSession(); sess.cookies_str = cookies_str
    if sess.is_valid(): _save(sess)
    return sess

def _search_sync(keyword: str, count: int = 20, page: int = 1) -> list[dict]:
    sess = _load()
    if not sess.is_valid(): return []
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "cookie": sess.cookies_str,
        "referer": "https://tieba.baidu.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "x-requested-with": "XMLHttpRequest",
    }
    params = {"rn": str(min(count, 20)), "st": "1", "word": keyword, "needbrand": "1", "sug_type": "2", "pn": str(page), "come_from": "search", "subapp_type": "pc", "_client_type": "20"}
    params["sign"] = _tieba_sign(params)
    kwargs = {"params": params, "headers": headers, "impersonate": "chrome124", "timeout": 15}
    try:
        from src.utils.http_client import create_curl_cffi_proxy
        proxy = create_curl_cffi_proxy()
        if proxy:
            kwargs["proxies"] = proxy
    except Exception:
        pass
    resp = curl_requests.get(SEARCH_URL, **kwargs)
    data = resp.json()
    if data.get("no") != 0 and data.get("error") != "success":
        return []
    results = []
    card_list = data.get("data", {}).get("card_list", []) or []
    for card in card_list:
        if not isinstance(card, dict):
            continue

        # Some responses wrap data in card["data"], others don't
        inner = card.get("data", card)
        if isinstance(inner, list):
            inner = inner[0] if inner else {}
        if not isinstance(inner, dict):
            continue

        # Type 1: Thread card — directly has tid, title, content
        if "tid" in inner and "title" in inner:
            user = inner.get("user") or {}
            replies = inner.get("post_num", 0)
            results.append({
                "title": inner.get("title", ""),
                "excerpt": (inner.get("content", "") or "")[:200],
                "url": f"https://tieba.baidu.com/p/{inner.get('tid', '')}",
                "replies": replies,
                "plays": replies,  # 贴吧用回复数代理热度
                "likes": 0,
                "author": user.get("user_name", "") or user.get("show_nickname", ""),
                "forum": inner.get("forum_name", ""),
                "tid": str(inner.get("tid", "")),
            })
            continue

        # Type 2: ExactMatch card — forum info + nested thread_list
        em = inner.get("exactMatch") or {}
        if em:
            results.append({
                "title": em.get("forum_name_show", "") or em.get("forum_name", ""),
                "excerpt": f"贴吧: {em.get('forum_name_show', em.get('forum_name', ''))} (帖子数: {em.get('post_num_ori', 0)})",
                "url": f"https://tieba.baidu.com/f?kw={urlquote(em.get('forum_name', ''))}",
                "replies": em.get("post_num_ori", 0),
                "author": "",
                "forum": em.get("forum_name_show", "") or em.get("forum_name", ""),
                "tid": str(em.get("forum_id", "")),
            })
            for t in em.get("thread_list", []) or []:
                author = t.get("author", {}) or {}
                replies = t.get("reply_num", 0)
                results.append({
                    "title": t.get("title", ""),
                    "excerpt": (t.get("abstract", "") or "")[:200],
                    "url": f"https://tieba.baidu.com/p/{t.get('tid', '')}",
                    "replies": replies,
                    "plays": replies,
                    "likes": 0,
                    "author": author.get("name", ""),
                    "forum": t.get("fname", ""),
                    "tid": str(t.get("tid", "")),
                })
    return results

async def search(keyword: str, count: int = 20, page: int = 1) -> list[dict]:
    return await asyncio.to_thread(_search_sync, keyword, count, page)

async def search_all(keyword: str, limit: int = 40) -> list[dict]:
    all_results, seen, page = [], set(), 1
    while len(all_results) < limit:
        items = await search(keyword, count=20, page=page)
        if not items: break
        new = [i for i in items if i.get("tid", i["title"]) not in seen and i.get("url", "")]
        for i in new: seen.add(i.get("tid", i["title"]))
        all_results.extend(new)
        page += 1
    return all_results[:limit]
