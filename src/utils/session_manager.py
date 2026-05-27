"""会话自动管理 — 健康检测 + 过期自动收割 + CDP 兜底。"""
import asyncio, json, logging, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from curl_cffi import requests as curl_requests

logger = logging.getLogger(__name__)
BROWSER_DATA = Path(__file__).resolve().parent.parent.parent / "browser_data"

# ── 平台注册表 ────────────────────────────────────────────
_PLATFORMS: dict[str, dict] = {}


def _register(name: str, session_file: str, health_url: str, health_params: dict,
              cookie_keys: list[str], harvest_func: str, use_curl: bool = False,
              method: str = "GET", extract_cookies: Optional[str] = None,
              health_ok_check: Optional[str] = None, extra_headers: Optional[dict] = None):
    _PLATFORMS[name] = {
        "name": name,
        "session_file": str(BROWSER_DATA / session_file),
        "health_url": health_url,
        "health_params": health_params,
        "cookie_keys": cookie_keys,
        "harvest_func": harvest_func,
        "use_curl": use_curl,
        "method": method,
        "extract_cookies": extract_cookies,
        "health_ok_check": health_ok_check,
        "extra_headers": extra_headers or {},
    }


# 抖音 — sessionid + ttwid + uifid
_register("douyin",
    session_file="session_context.json",
    health_url="https://www.douyin.com/aweme/v1/web/general/search/single/",
    health_params={"keyword": "test", "search_channel": "aweme_general", "search_source": "normal_search", "query_correct_type": "1", "is_filter_search": "0", "offset": "0", "count": "1", "need_filter_settings": "0", "cookie_enabled": "true", "screen_width": "1920", "screen_height": "1080", "browser_language": "zh-CN", "browser_platform": "Win32", "browser_name": "Chrome", "browser_version": "148.0.0.0", "browser_online": "true", "engine_name": "Blink", "engine_version": "148.0.0.0", "os_name": "Windows", "os_version": "10", "cpu_core_num": "8", "device_memory": "8", "platform": "PC", "downlink": "10", "effective_type": "4g", "round_trip_time": "50"},
    cookie_keys=["sessionid", "ttwid", "uifid"],
    harvest_func="src.utils.douyin_http:harvest_from_cdp",
    health_ok_check="data",
)

# 小红书 — cookies + x-s (POST!)
_register("xiaohongshu",
    session_file="xhs_http_session.json",
    health_url="https://edith.xiaohongshu.com/api/sns/web/v1/search/notes",
    health_params={"keyword": "test", "page": "1", "page_size": "1", "search_id": "test", "sort": "general", "note_type": "0"},
    cookie_keys=["cookies_str", "xs_common", "xs", "xt"],
    harvest_func="src.utils.xhs_http:harvest_from_cdp",
    method="POST",
    extra_headers={"content-type": "application/json;charset=UTF-8", "origin": "https://www.xiaohongshu.com", "referer": "https://www.xiaohongshu.com/"},
    health_ok_check="data",
)

# 快手 — cookies only
_register("kuaishou",
    session_file="ks_http_session.json",
    health_url="https://www.kuaishou.com/rest/v/search/feed",
    health_params={"keyword": "test", "pcursor": "", "searchSessionId": "test"},
    cookie_keys=["cookies_str"],
    harvest_func="src.utils.ks_http:harvest_from_cdp",
    health_ok_check="items",
)

# 知乎 — cookies only
_register("zhihu",
    session_file="zh_http_session.json",
    health_url="https://www.zhihu.com/api/v4/search_v3",
    health_params={"gk_version": "gz-gaokao", "t": "general", "q": "test", "correction": "1", "offset": "0", "limit": "1", "lc_idx": "0", "show_all_topics": "0", "search_source": "Normal"},
    cookie_keys=["cookies_str"],
    harvest_func="src.utils.zh_http:harvest_from_cdp",
    health_ok_check="data",
)

# 微博 — cookies + x-xsrf-token
_register("weibo",
    session_file="weibo_http_session.json",
    health_url="https://weibo.com/ajax/statuses/search",
    health_params={"q": "test", "page": "1", "count": "1"},
    cookie_keys=["cookies_str", "xsrf_token"],
    harvest_func="src.utils.weibo_http:harvest_from_cdp",
    health_ok_check="statuses",
)

# B站 — 纯 Python Wbi hashlib，零 JS 引擎
_register("bilibili",
    session_file="bilibili_session.json",
    health_url="https://api.bilibili.com/x/web-interface/wbi/search/type",
    health_params={"keyword": "美食", "search_type": "video", "page": "1", "page_size": "1"},
    cookie_keys=["cookies_str", "wbi_img_key", "wbi_sub_key"],
    harvest_func="src.utils.bilibili_http:harvest_from_cdp",
    health_ok_check="data",
)

# 贴吧 — cookies + curl_cffi
_register("tieba",
    session_file="tieba_http_session.json",
    health_url="https://tieba.baidu.com/mo/q/search/multsearch",
    health_params={"rn": "1", "st": "1", "word": "test", "needbrand": "0", "sug_type": "0", "pn": "1", "come_from": "search", "subapp_type": "pc", "_client_type": "20"},
    cookie_keys=["cookies_str"],
    harvest_func="src.utils.tieba_http:harvest_from_cdp",
    use_curl=True,
    health_ok_check="data",
)


def _import_func(func_path: str):
    """动态导入 module:function"""
    mod_path, func_name = func_path.split(":")
    import importlib
    mod = importlib.import_module(mod_path)
    return getattr(mod, func_name)


def _check_cdp_available(port: int = 9222) -> bool:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        result = s.connect_ex(("127.0.0.1", port))
        s.close()
        return result == 0
    except:
        return False


async def check_health(platform: str) -> bool:
    """快速健康检测 — 用平台自己的 search 做个最小调用。"""
    cfg = _PLATFORMS.get(platform)
    if not cfg:
        return False

    session_path = Path(cfg["session_file"])
    if not session_path.exists():
        return False

    # 用对应模块的 search 函数做轻量调用（用常见词确保有结果）
    try:
        if platform == "douyin":
            from src.utils.douyin_http import search
            items = await search("美食", count=1)
            return len(items) > 0
        elif platform == "xiaohongshu":
            from src.utils.xhs_http import search
            items = await search("美食", count=1)
            return len(items) >= 0  # XHS 返回空列表都算会话有效
        elif platform == "kuaishou":
            from src.utils.ks_http import search
            items = await search("美女", count=1)
            return len(items) > 0
        elif platform == "zhihu":
            from src.utils.zh_http import search
            items = await search("美食", count=1)
            return len(items) > 0
        elif platform == "weibo":
            from src.utils.weibo_http import search
            items = await search("美食", count=1)
            return len(items) > 0
        elif platform == "bilibili":
            from src.utils.bilibili_http import search
            items = await search("美食", count=1)
            return len(items) > 0
        elif platform == "tieba":
            from src.utils.tieba_http import search
            items = await search("美食", count=1)
            return len(items) > 0
    except:
        pass
    return False


def _build_headers(platform: str, cookies_str: str, session: dict) -> dict:
    headers = {
        "accept": "application/json, text/plain, */*",
        "cookie": cookies_str,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    }
    if platform == "weibo":
        xsrf = session.get("xsrf_token", "")
        headers.update({
            "referer": "https://s.weibo.com/",
            "x-requested-with": "XMLHttpRequest",
            "x-xsrf-token": xsrf,
            "client-version": "3.0.0",
            "server-version": "v2026.05.25.1",
        })
    elif platform == "xiaohongshu":
        headers["content-type"] = "application/json;charset=UTF-8"
        headers["origin"] = "https://www.xiaohongshu.com"
        headers["referer"] = "https://www.xiaohongshu.com/"
    elif platform == "kuaishou":
        headers["referer"] = "https://www.kuaishou.com/"
        headers["content-type"] = "application/json"
    elif platform == "zhihu":
        headers["referer"] = "https://www.zhihu.com/search?type=content&q=test"
        headers["x-api-version"] = "3.0.91"
    elif platform == "tieba":
        headers["referer"] = "https://tieba.baidu.com/"
        headers["x-requested-with"] = "XMLHttpRequest"
    return headers


async def ensure_session(platform: str, port: int = 9222) -> bool:
    """确保会话有效。先健康检测，过期则自动收割。"""
    cfg = _PLATFORMS.get(platform)
    if not cfg:
        logger.warning(f"[session-manager] 未知平台: {platform}")
        return False

    # 1. 健康检测
    if await check_health(platform):
        return True

    # 2. 会话过期，尝试自动收割
    logger.info(f"[session-manager] {platform} 会话过期，尝试自动收割...")
    if not _check_cdp_available(port):
        logger.warning(f"[session-manager] CDP Chrome 未运行，无法自动收割 {platform}")
        return False

    try:
        harvest_fn = _import_func(cfg["harvest_func"])
        sess = await harvest_fn(port)
        if sess.is_valid():
            logger.info(f"[session-manager] {platform} 会话收割成功")
            return True
    except Exception as exc:
        logger.error(f"[session-manager] {platform} 收割失败: {exc}")

    return False


async def harvest_all(port: int = 9222) -> dict[str, bool]:
    """全部平台收割一次。"""
    results = {}
    for name in _PLATFORMS:
        try:
            harvest_fn = _import_func(_PLATFORMS[name]["harvest_func"])
            sess = await harvest_fn(port)
            results[name] = sess.is_valid()
            logger.info(f"[session-manager] {name}: {'OK' if results[name] else 'FAIL'}")
        except Exception as exc:
            results[name] = False
            logger.error(f"[session-manager] {name} 收割异常: {exc}")
    return results


def list_platforms() -> list[str]:
    return sorted(_PLATFORMS.keys())


def session_info(platform: str) -> dict:
    cfg = _PLATFORMS.get(platform)
    if not cfg:
        return {"error": f"未知平台: {platform}"}
    session_path = Path(cfg["session_file"])
    info = {"platform": platform, "session_file": str(session_path), "exists": session_path.exists()}
    if session_path.exists():
        try:
            data = json.loads(session_path.read_text("utf-8"))
            info["harvested_at"] = data.get("harvested_at", "?")
            info["cookies_len"] = len(data.get("cookies_str", ""))
        except:
            info["parse_error"] = True
    return info
