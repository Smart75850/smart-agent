"""Proxy 輪換池 — round-robin 多 proxy 支援。"""

import os
from typing import Optional

from config.settings import settings


class ProxyManager:
    """多 Proxy 輪換管理器。

    資料來源優先級：
    1. proxy_list 參數（程式碼注入）
    2. proxy_url 參數
    3. PROXY_LIST 環境變數（逗號分隔）
    4. settings.PROXY_URL
    """

    def __init__(self, proxy_url: Optional[str] = None, proxy_list: Optional[list[str]] = None):
        self._proxies: list[str] = []
        # 標記是否顯式傳入（繞過 settings.PROXY_ENABLED 開關）
        self._explicit = proxy_url is not None or proxy_list is not None

        if proxy_list:
            for p in proxy_list:
                p = p.strip()
                if p and p not in self._proxies:
                    self._proxies.append(p)

        if proxy_url and proxy_url not in self._proxies:
            self._proxies.append(proxy_url)

        env_list = os.environ.get("PROXY_LIST", "")
        if env_list:
            for p in env_list.split(","):
                p = p.strip()
                if p and p not in self._proxies:
                    self._proxies.append(p)

        if settings.PROXY_URL and settings.PROXY_URL not in self._proxies:
            self._proxies.append(settings.PROXY_URL)

        self._index = 0

    def get_playwright_proxy(self) -> Optional[dict]:
        if not self._proxies:
            return None
        if not self._explicit and not settings.PROXY_ENABLED:
            return None
        proxy = self._proxies[self._index % len(self._proxies)]
        self._index += 1
        return {"server": proxy}

    def get_next_proxy(self) -> Optional[str]:
        """返回原始 proxy URL（唔包 Playwright dict），畀 AccountManager fallback 用。"""
        if not self._proxies:
            return None
        if not self._explicit and not settings.PROXY_ENABLED:
            return None
        proxy = self._proxies[self._index % len(self._proxies)]
        self._index += 1
        return proxy

    @property
    def enabled(self) -> bool:
        if self._explicit:
            return bool(self._proxies)
        return bool(self._proxies) and settings.PROXY_ENABLED
