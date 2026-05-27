"""B站纯 HTTP 搜索客户端 — Wbi 签名 (纯 Python hashlib，零浏览器)。"""
import json, logging
from pathlib import Path
from datetime import datetime
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.bilibili.com/x/web-interface/wbi/search/type"
SESSION_FILE = Path(__file__).resolve().parent.parent.parent / "browser_data/bilibili_session.json"

_WBI_MIXIN_KEY_TABLE = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3,
    45, 35, 27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39,
    12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61, 26, 17,
    0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63,
    57, 62, 11, 36, 20, 52, 44, 34,
]

import hashlib, time, re

class BilibiliSession:
    __slots__ = ("cookies_str", "wbi_img_key", "wbi_sub_key", "key_ts", "harvested_at")

    def __init__(self):
        self.cookies_str = ""
        self.wbi_img_key = ""
        self.wbi_sub_key = ""
        self.key_ts = 0.0
        self.harvested_at = ""

    def is_valid(self) -> bool:
        return bool(self.wbi_img_key and self.wbi_sub_key)

    def to_dict(self) -> dict:
        return {
            "cookies_str": self.cookies_str,
            "wbi_img_key": self.wbi_img_key,
            "wbi_sub_key": self.wbi_sub_key,
            "key_ts": self.key_ts,
            "harvested_at": self.harvested_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BilibiliSession":
        s = cls()
        s.cookies_str = d.get("cookies_str", "")
        s.wbi_img_key = d.get("wbi_img_key", "")
        s.wbi_sub_key = d.get("wbi_sub_key", "")
        s.key_ts = d.get("key_ts", 0)
        s.harvested_at = d.get("harvested_at", "")
        return s


def _load_session() -> BilibiliSession:
    if SESSION_FILE.exists():
        try:
            return BilibiliSession.from_dict(json.loads(SESSION_FILE.read_text("utf-8")))
        except (json.JSONDecodeError, KeyError):
            pass
    return BilibiliSession()


def _save_session(sess: BilibiliSession):
    sess.harvested_at = datetime.now().isoformat()
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(sess.to_dict(), ensure_ascii=False, indent=2), "utf-8")


def _get_mixin_key(raw: str) -> str:
    return "".join(raw[i] for i in _WBI_MIXIN_KEY_TABLE[:32])


def _extract_key(url: str) -> str:
    m = re.search(r"wbi/([^./]+)", url)
    return m.group(1) if m else ""


async def fetch_wbi_keys() -> tuple[str, str]:
    """从 B站 nav API 获取 wbi_img key。"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.bilibili.com/x/web-interface/nav",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        data = resp.json().get("data", {})
        wbi_img = data.get("wbi_img", {})
        img_url = wbi_img.get("img_url", "")
        sub_url = wbi_img.get("sub_url", "")
        return _extract_key(img_url), _extract_key(sub_url)


async def harvest_from_cdp(port: int = 9222) -> BilibiliSession:
    """从 CDP Chrome 收割 B站 cookies + wbi keys。"""
    import os
    os.environ["no_proxy"] = "127.0.0.1,localhost"
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        context = browser.contexts[0]
        all_cookies = await context.cookies()
        bili_cookies = [c for c in all_cookies if "bilibili" in c.get("domain", "")]
        cookies_str = "; ".join(f"{c['name']}={c['value']}" for c in bili_cookies)
        await browser.close()

    img_key, sub_key = await fetch_wbi_keys()

    sess = BilibiliSession()
    sess.cookies_str = cookies_str
    sess.wbi_img_key = img_key
    sess.wbi_sub_key = sub_key
    sess.key_ts = time.time()
    if sess.is_valid():
        _save_session(sess)
    return sess


async def search(keyword: str, count: int = 20, page: int = 1) -> list[dict]:
    """B站纯 HTTP 搜索 — Wbi 签名。"""
    sess = _load_session()

    # wbi keys 过期刷新
    img_key, sub_key = sess.wbi_img_key, sess.wbi_sub_key
    if not img_key or not sub_key or time.time() - sess.key_ts > 3600:
        try:
            img_key, sub_key = await fetch_wbi_keys()
            sess.wbi_img_key = img_key
            sess.wbi_sub_key = sub_key
            sess.key_ts = time.time()
            if sess.is_valid():
                _save_session(sess)
        except Exception:
            if not img_key:
                logger.warning("[bilibili-http] 无法获取 wbi keys")
                return []

    if not img_key or not sub_key:
        return []

    mixin_key = _get_mixin_key(img_key + sub_key)

    params = {
        "search_type": "video",
        "keyword": keyword,
        "page": str(page),
        "page_size": str(min(count, 50)),
    }
    params["wts"] = int(time.time())
    sorted_params = sorted(params.items())
    query = "&".join(f"{k}={v}" for k, v in sorted_params)
    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
    params["w_rid"] = w_rid

    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "referer": f"https://search.bilibili.com/all?keyword={quote(keyword)}",
    }
    if sess.cookies_str:
        headers["cookie"] = sess.cookies_str

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(SEARCH_URL, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    if data.get("code", -1) != 0:
        logger.warning(f"[bilibili-http] API code={data.get('code')} msg={data.get('message','')}")
        return []

    results = []
    for item in (data.get("data", {}).get("result") or []):
        results.append({
            "title": item.get("title", "").replace('<em class="keyword">', "").replace("</em>", ""),
            "author": item.get("author", ""),
            "play_count": item.get("play", 0),
            "likes": item.get("favorites", 0),
            "duration": item.get("duration", ""),
            "bvid": item.get("bvid", ""),
            "link": (item.get("arcurl", "") or "").replace("http://", "https://") or f"https://www.bilibili.com/video/{item.get('bvid','')}",
            "description": item.get("description", ""),
            "pubdate": item.get("pubdate", 0),
        })

    return results


async def search_all(keyword: str, limit: int = 40) -> list[dict]:
    """分页获取搜索结果直到达到 limit。"""
    all_results = []
    seen_ids = set()
    page = 1
    while len(all_results) < limit and page < 15:
        items = await search(keyword, count=min(50, limit - len(all_results)), page=page)
        if not items:
            break
        new_items = [i for i in items if i["bvid"] not in seen_ids]
        for item in new_items:
            seen_ids.add(item["bvid"])
        all_results.extend(new_items)
        page += 1
    return all_results[:limit]
