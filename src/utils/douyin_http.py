"""抖音纯 HTTP 搜索客户端 — 零浏览器依赖。

基于收割的会话上下文（sessionid + ttwid + uifid），
直接发 HTTP 请求到抖音搜索 API，唔需要浏览器。
"""
import json, random, string, logging
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
