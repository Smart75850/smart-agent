"""抖音纯 HTTP 搜索客户端 — 零浏览器依赖。

基于收割的会话上下文（sessionid + ttwid + uifid），
直接发 HTTP 请求到抖音搜索 API，唔需要浏览器。
"""
import asyncio, json, random, string, logging, time
from datetime import datetime
from urllib.parse import quote
import httpx

from src.utils.session_context import session_store, DouyinSession

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.douyin.com/aweme/v1/web/general/search/single/"

FIXED_PARAMS = {
    "device_platform": "webapp",
    "aid": "6383",
    "channel": "channel_pc_web",
    "cookie_enabled": "true",
    "browser_language": "zh-CN",
    "browser_name": "Chrome",
    "browser_online": "true",
    "browser_platform": "Win32",
    "browser_version": "148.0.0.0",
    "cpu_core_num": "16",
    "device_memory": "32",
    "downlink": "10",
    "effective_type": "4g",
    "enable_history": "1",
    "engine_name": "Blink",
    "engine_version": "148.0.0.0",
    "is_filter_search": "0",
    "list_type": "single",
    "need_filter_settings": "0",
    "os_name": "Windows",
    "os_version": "10",
    "pc_client_type": "1",
    "pc_libra_divert": "Windows",
    "pc_search_top_1_params": '{"enable_ai_search_top_1":1}',
    "platform": "PC",
    "query_correct_type": "1",
    "round_trip_time": "50",
    "screen_height": "864",
    "screen_width": "1536",
    "search_channel": "aweme_general",
    "search_source": "normal_search",
    "support_dash": "1",
    "support_h265": "1",
    "update_version_code": "170400",
    "version_code": "190600",
    "version_name": "19.6.0",
    "disable_rs": "0",
}


def _make_search_id() -> str:
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    rand_hex = ''.join(random.choices(string.hexdigits.upper(), k=18))
    return f"{ts}{rand_hex}"


def _build_headers(session: DouyinSession, keyword: str, search_id: str) -> dict:
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "cookie": session.to_cookie_header(),
        "referer": f"https://www.douyin.com/search/{quote(keyword)}",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "uifid": session.uifid,
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
    }


async def search(keyword: str, count: int = 20, offset: int = 0) -> list[dict]:
    """纯 HTTP 抖音搜索，返回视频列表。"""
    session = session_store.session
    if not session.is_valid():
        logger.warning("会话上下文无效，请先运行收割脚本")
        return []

    search_id = _make_search_id()

    params = dict(FIXED_PARAMS)
    params["keyword"] = keyword
    params["count"] = str(min(count, 20))
    params["offset"] = str(offset)
    params["uifid"] = session.uifid
    params["search_id"] = search_id

    # 本地生成 a_bogus 签名
    try:
        from src.utils.abogus import ABogus, DEFAULT_UA
        ab = ABogus(user_agent=DEFAULT_UA)
        params["a_bogus"] = ab.get_value(params, method="GET")
    except Exception as e:
        logger.debug(f"a_bogus 生成失败: {e}")

    headers = _build_headers(session, keyword, search_id)

    from src.utils.http_client import create_httpx_client
    async with create_httpx_client(15) as client:
        resp = await client.get(SEARCH_URL, params=params, headers=headers)
        resp.raise_for_status()
        body = resp.json()

    status_code = body.get("status_code", -1)
    if status_code != 0:
        nil_info = body.get("search_nil_info", {}) or {}
        nil_type = nil_info.get("search_nil_type", "")
        logger.warning(f"搜索被拒: status_code={status_code}, nil_type='{nil_type}'")
        return []

    items = body.get("data") or []
    results = []
    seen = set()

    for item in items:
        info = item.get("aweme_info", item)
        aweme_id = str(info.get("aweme_id", ""))
        if not aweme_id or aweme_id in seen:
            continue
        seen.add(aweme_id)

        # 提取统计数据
        statistics = info.get("statistics", {}) or {}
        results.append({
            "title": info.get("desc", ""),
            "author": info.get("author", {}).get("nickname", ""),
            "plays": statistics.get("play_count", 0) or statistics.get("share_count", 0) or 0,
            "likes": statistics.get("digg_count", 0) or 0,
            "comments": statistics.get("comment_count", 0) or 0,
            "shares": statistics.get("share_count", 0) or 0,
            "collects": statistics.get("collect_count", 0) or 0,
            "aweme_id": aweme_id,
            "sec_uid": info.get("author", {}).get("sec_uid", ""),
            "cover_url": (info.get("video", {}).get("cover", {}).get("url_list", [""]) or [""])[0],
            "link": f"https://www.douyin.com/video/{aweme_id}" if aweme_id else "",
        })

    return results


async def search_all(keyword: str, limit: int = 40) -> list[dict]:
    """分页获取搜索结果直到达到 limit。"""
    all_results = []
    seen_ids = set()
    offset = 0
    max_attempts = (limit // 10) + 5
    attempts = 0
    while len(all_results) < limit and attempts < max_attempts:
        batch = await search(keyword, count=min(20, limit - len(all_results)), offset=offset)
        attempts += 1
        if not batch:
            break
        new_items = [r for r in batch if r["aweme_id"] not in seen_ids]
        for item in new_items:
            seen_ids.add(item["aweme_id"])
        all_results.extend(new_items)
        offset += len(batch)
    return all_results[:limit]


# ── 会话收割（session_manager 需要）──────────────────────────

async def harvest_from_cdp(port: int = 9222):
    """从 CDP Chrome 收割抖音会话。"""
    return await session_store.harvest_from_cdp(port)


async def harvest_persistent():
    """使用持久化 Playwright Profile 收割抖音会话。"""
    import asyncio, os
    os.environ["no_proxy"] = "127.0.0.1,localhost"
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    from playwright.async_api import async_playwright
    from pathlib import Path

    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    profile_dir = str(_PROJECT_ROOT / "browser_data" / "douyin_profile")
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            profile_dir, headless=False,
            viewport={"width": 1280, "height": 800}, locale="zh-CN",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.douyin.com", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        cookies = await context.cookies()
        has_sessionid = any(c['name'] == 'sessionid' for c in cookies)
        if not has_sessionid:
            logger.warning("抖音未登录（缺少 sessionid），请在弹出窗口中扫码登录...")
            for i in range(90):
                await asyncio.sleep(2)
                cookies = await context.cookies()
                if any(c['name'] == 'sessionid' for c in cookies):
                    logger.info("抖音登录成功")
                    break
                if i % 15 == 0:
                    logger.info(f"  等待登录... ({i*2}s)")

        cookies = await context.cookies()
        cookies_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        cookie_map = {c['name']: c['value'] for c in cookies}

        from datetime import datetime
        sess = DouyinSession(
            ttwid=cookie_map.get("ttwid", ""),
            sessionid=cookie_map.get("sessionid", ""),
            uifid=cookie_map.get("UIFID", ""),
            odin_tt=cookie_map.get("odin_tt", ""),
            passport_csrf_token=cookie_map.get("passport_csrf_token", ""),
            cookies_str=cookies_str,
            harvested_at=datetime.now().isoformat(),
        )
        if sess.is_valid():
            session_store._session = sess
        await context.close()
        return sess


# ── 反反爬：请求速率控制 ─────────────────────────────────────

class _RateLimiter:
    def __init__(self):
        self._last_call = 0.0
        self._consecutive_failures = 0
        self._cooldown_until = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.time()
            if now < self._cooldown_until:
                return False
            min_gap = random.uniform(2.0, 5.0)
            since_last = now - self._last_call
            if since_last < min_gap:
                await asyncio.sleep(min_gap - since_last)
            self._last_call = time.time()
            return True

    def report_failure(self, is_blocked=False):
        self._consecutive_failures += 1
        if is_blocked:
            backoff = min(30 * (2 ** min(self._consecutive_failures, 4)), 480)
            self._cooldown_until = time.time() + backoff + random.uniform(0, backoff * 0.3)

    @property
    def in_cooldown(self):
        return time.time() < self._cooldown_until


_rate_limiter = _RateLimiter()
