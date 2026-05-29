"""B站纯 HTTP 客户端 — Wbi 签名 + curl_cffi TLS 指纹伪装，零浏览器。"""
import json
from pathlib import Path
from datetime import datetime
from urllib.parse import quote

from curl_cffi import requests as cffi_requests

from src.utils.logger import logger

SEARCH_URL = "https://api.bilibili.com/x/web-interface/wbi/search/type"
USER_VIDEOS_URL = "https://api.bilibili.com/x/space/arc/search"
SESSION_FILE = Path(__file__).resolve().parent.parent.parent / "browser_data/bilibili_session.json"

# curl_cffi TLS 指纹伪装（chrome124 实测可绕过 B站 WAF）
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

_WBI_MIXIN_KEY_TABLE = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3,
    45, 35, 27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39,
    12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61, 26, 17,
    0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63,
    57, 62, 11, 36, 20, 52, 44, 34,
]

import hashlib, time, re, random

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
    resp = _get_http_session().get(
        "https://api.bilibili.com/x/web-interface/nav",
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        impersonate=_IMPERSONATE,
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


async def _wbi_get(url: str, params: dict, referer: str) -> dict | None:
    """发送带 Wbi 签名的 GET 请求，返回 data dict 或 None。"""
    sess = _load_session()
    img_key, sub_key = sess.wbi_img_key, sess.wbi_sub_key

    if not img_key or not sub_key or time.time() - sess.key_ts > 3600:
        try:
            img_key, sub_key = await fetch_wbi_keys()
            sess.wbi_img_key = img_key
            sess.wbi_sub_key = sub_key
            sess.key_ts = time.time()
            if sess.is_valid():
                _save_session(sess)
        except Exception as e:
            logger.error(f"[bilibili-http] wbi keys refresh failed: {e}")
            if not img_key:
                return None

    if not img_key or not sub_key:
        return None

    mixin_key = _get_mixin_key(img_key + sub_key)
    params["wts"] = int(time.time())
    sorted_params = sorted(params.items())
    query = "&".join(f"{k}={v}" for k, v in sorted_params)
    params["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()

    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "referer": referer,
    }
    if sess.cookies_str:
        headers["cookie"] = sess.cookies_str

    resp = _get_http_session().get(url, params=params, headers=headers, impersonate=_IMPERSONATE)
    resp.raise_for_status()
    data = resp.json()

    code = data.get("code", -1)
    if code != 0:
        logger.warning(f"[bilibili-http] API code={code} msg={data.get('message','')}")
        if code == -799:  # 被限流，切账号
            try:
                from src.utils.session_manager import mark_rate_limited
                mark_rate_limited("bilibili")
            except Exception:
                pass
        return None
    return data.get("data")


async def search(keyword: str, count: int = 20, page: int = 1) -> list[dict]:
    """B站纯 HTTP 搜索 — Wbi 签名。"""
    params = {
        "search_type": "video",
        "keyword": keyword,
        "page": str(page),
        "page_size": str(min(count, 50)),
        "order": "click",  # 按播放量排序，结果更热门
    }
    data = await _wbi_get(SEARCH_URL, params, f"https://search.bilibili.com/all?keyword={quote(keyword)}")
    if not data:
        return []

    results = []
    for item in (data.get("result") or []):
        results.append({
            "title": item.get("title", "").replace('<em class="keyword">', "").replace("</em>", ""),
            "author": item.get("author", ""),
            "play_count": item.get("play", 0),
            "likes": item.get("favorites", 0),
            "duration": item.get("duration", ""),
            "bvid": item.get("bvid", ""),
            "link": (item.get("arcurl", "") or "").replace("http://", "https://") or f"https://www.bilibili.com/video/{item.get('bvid','')}",
            "cover_url": "https:" + item.get("pic", "") if item.get("pic", "").startswith("//") else item.get("pic", ""),
            "mid": item.get("mid", ""),
            "description": item.get("description", ""),
            "pubdate": item.get("pubdate", 0),
        })
    return results


async def fetch_user_videos(mid: str, limit: int = 40, page: int = 1) -> list[dict]:
    """B站纯 HTTP 获取用户主页视频 — 非 Wbi 端点，无需签名。"""
    params = {
        "mid": mid,
        "ps": str(min(limit, 50)),
        "pn": str(page),
        "order": "pubdate",
        "platform": "web",
        "web_location": "1550101",
    }
    sess = _load_session()
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "referer": f"https://space.bilibili.com/{mid}/video",
        "origin": "https://space.bilibili.com",
    }
    if sess.cookies_str:
        headers["cookie"] = sess.cookies_str

    resp = _get_http_session().get(USER_VIDEOS_URL, params=params, headers=headers, impersonate=_IMPERSONATE)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code", -1) != 0:
        logger.warning(f"[bilibili-http] user video API code={data.get('code')} msg={data.get('message','')}")
        return []
    if not data:
        return []

    results = []
    for item in (data.get("list", {}).get("vlist") or []):
        bvid = item.get("bvid", "")
        results.append({
            "title": item.get("title", ""),
            "author": item.get("author", ""),
            "play_count": item.get("play", 0),
            "likes": item.get("favorites", 0),
            "duration": item.get("length", ""),
            "bvid": bvid,
            "link": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
            "mid": str(item.get("mid", mid)),
            "description": item.get("description", ""),
            "pubdate": item.get("created", 0),
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


async def get_video_url(bvid: str) -> str:
    """纯 HTTP 获取 B站视频 CDN 下载地址（无需浏览器）。

    流程：bvid → view API 拿 cid → playurl API 拿 CDN URL。
    """
    from curl_cffi import requests as cffi_requests

    # Step 1: 用 bvid 获取 aid 和 cid
    view_url = "https://api.bilibili.com/x/web-interface/view"
    view_params = {"bvid": bvid}
    data = await _wbi_get(view_url, view_params, f"https://www.bilibili.com/video/{bvid}")
    if not data:
        return ""
    aid = data.get("aid", 0)
    cid = data.get("cid", 0)
    if not aid or not cid:
        # 尝试从 pages 数组拿第一个分P的 cid
        pages = data.get("pages", [])
        cid = pages[0].get("cid", 0) if pages else 0
    if not aid or not cid:
        return ""

    # Step 2: 获取视频播放地址
    play_url = "https://api.bilibili.com/x/player/wbi/playurl"
    play_params = {"avid": aid, "cid": cid, "qn": 80, "fourk": 1, "fnval": 1, "platform": "pc"}
    play_data = await _wbi_get(play_url, play_params, f"https://www.bilibili.com/video/{bvid}")
    if not play_data:
        return ""

    # Step 3: 选最高画质
    durl = play_data.get("durl", [])
    if not durl:
        return ""
    best = max(durl, key=lambda d: d.get("size", 0))
    return best.get("url", "")


async def download_media(url: str, filepath: str) -> bool:
    """纯 HTTP 流式下载媒体文件（独立客户端，无签名头，跟随重定向）。"""
    from curl_cffi import requests as cffi_requests
    from pathlib import Path

    fp = Path(filepath)
    fp.parent.mkdir(parents=True, exist_ok=True)
    if fp.exists() and fp.stat().st_size > 0:
        return True  # 已存在，跳过

    try:
        session = cffi_requests.Session()
        session.timeout = 120
        resp = session.get(url, impersonate="chrome124", stream=True)
        if resp.status_code not in (200, 206):
            return False
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        return True
    except Exception:
        return False


async def fetch_user_profile(mid: str) -> dict:
    """B站纯 HTTP 获取用户资料：昵称/头像/粉丝数/作品数。"""
    sess = _load_session()
    headers = {
        "accept": "application/json",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "referer": f"https://space.bilibili.com/{mid}",
    }
    if sess.cookies_str:
        headers["cookie"] = sess.cookies_str

    profile = {"nickname": "", "avatar": "", "follower_count": 0, "video_count": 0, "mid": mid}

    # 1. 用户基本信息（非 Wbi 端点）
    try:
        resp = _get_http_session().get(
            "https://api.bilibili.com/x/web-interface/card",
            params={"mid": mid, "platform": "web"},
            headers=headers, impersonate=_IMPERSONATE,
        )
        data = resp.json()
        if data.get("code") == 0:
            card = data.get("data", {}).get("card", {})
            profile["nickname"] = card.get("name", "")
            profile["avatar"] = card.get("face", "")
            profile["follower_count"] = data.get("data", {}).get("follower", 0)
    except Exception:
        pass

    # 2. 作品数
    try:
        data = await _wbi_get(
            "https://api.bilibili.com/x/space/upstat",
            {"mid": mid},
            referer=f"https://space.bilibili.com/{mid}",
        )
        if data and isinstance(data.get("archive"), dict):
            profile["video_count"] = data["archive"].get("view", 0)
    except Exception:
        pass

    return profile
