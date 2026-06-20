from __future__ import annotations
"""HTTP 客户端工厂 — 自动注入代理，失败时降级直连。"""
import httpx
from src.utils.logger import logger
from config.settings import settings


def _get_proxy() -> str | None:
    if not settings.PROXY_ENABLED:
        return None
    try:
        from src.utils.proxy_pool import proxy_pool
        return proxy_pool.get_httpx_proxy()
    except Exception:
        return None


def create_httpx_client(timeout: float = 15) -> httpx.AsyncClient:
    proxy = _get_proxy()
    if proxy:
        logger.debug(f"[http_client] 使用代理: {proxy}")
    return httpx.AsyncClient(proxy=proxy, timeout=httpx.Timeout(timeout))


def create_curl_cffi_proxy() -> dict | None:
    """返回 curl_cffi 格式的代理字典，非方则返回 None。"""
    proxy_url = _get_proxy()
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}
