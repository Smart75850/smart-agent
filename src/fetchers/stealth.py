#!/usr/bin/env python3
"""
StealthFetcher — 全副武裝隱身瀏覽器（底層引擎：Scrapling StealthyFetcher）

三種運行模式（由強到弱）：
  1. CDP 模式（最強） → 連接已登入嘅真實 Chrome → CF 直接通過
  2. real_chrome 模式 → 用本機安裝嘅 Chrome → 真實指紋
  3. headless=False 模式 → 可視化 Chromium → 有 GPU 渲染

層內全自動（Scrapling 原生處理）：
  - Cloudflare Turnstile/Interstitial 自動破解
  - 廣告/追蹤域名攔截 (~3500 domains)
  - DNS-over-HTTPS 防洩漏
  - Canvas 指紋噪聲 + WebRTC 防護 + WebGL 控制
  - 動態 Headers + Google Referer 偽裝
  - 自動重試 + Proxy 故障切換

用法：
    # 最強：連接已登入 Chrome
    StealthFetcher.fetch_sync(url, cdp_url="http://127.0.0.1:9222")

    # 真實 Chrome 指紋
    StealthFetcher.fetch_sync(url, real_chrome=True, headless=False)

    # 可視化模式
    StealthFetcher.fetch_sync(url, headless=False)
"""

import re
from html.parser import HTMLParser
import os as _os
from typing import Optional

from config.settings import settings
from src.utils.logger import logger


def _detect_real_chrome() -> bool:
    """檢測本機是否有安裝 Google Chrome。

    用 real_chrome=True 時 CF 破解率顯著提升，因為真實 Chrome 嘅指紋
    比 Chromium 更難被檢測。
    """
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ]
    for p in chrome_paths:
        if _os.path.exists(p):
            return True
    # 檢查 PATH
    import shutil
    return shutil.which("google-chrome") is not None or shutil.which("chrome") is not None

# 🆕 自動檢測 real Chrome（預設 True 如果有安裝）
_HAS_REAL_CHROME = _detect_real_chrome()


class _TextExtractor(HTMLParser):
    """快速 HTML → 純文本提取"""
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip = {'script', 'style', 'nav', 'footer', 'header', 'code', 'pre', 'noscript'}

    def handle_data(self, data):
        t = data.strip()
        if t and len(t) > 1:
            self.text.append(t)


def _extract_text(html: str) -> str:
    try:
        e = _TextExtractor()
        e.feed(html)
        return "\n".join(e.text)
    except Exception:
        return re.sub(r'<[^>]+>', '', html)


class StealthFetcher:
    """全副武裝隱身瀏覽器 — Scrapling 引擎 + CDP 支持。

    三種模式（按破解力排序）：
      CDP > real_chrome + headful > headful > headless
    """

    headless: bool = True
    default_timeout: int = 30000
    max_text_length: int = 8000

    @staticmethod
    def _to_dict(page, fetcher_label: str = "stealth") -> dict:
        """將 Scrapling Response 轉換為 Smart Agent 統一格式。

        Scrapling Response 對象結構：
          page.text          → 純文本內容
          page.html_content  → 原始 HTML
          page.get_all_text()→ 提取所有文本
          page.status/url/headers/cookies
        """
        text = ""
        try:
            # 方式 1: page.text（Scrapling 原生純文本）
            if hasattr(page, 'text'):
                t = page.text
                if t and len(str(t)) > 50:
                    text = str(t)
            # 方式 2: html_content 提取
            if not text and hasattr(page, 'html_content'):
                raw = page.html_content
                if raw:
                    text = _extract_text(str(raw))
            # 方式 3: get_all_text
            if not text and hasattr(page, 'get_all_text'):
                t = page.get_all_text()
                if t:
                    text = str(t)
            if not text:
                text = str(page)
        except Exception:
            text = str(page)

        if len(text) > StealthFetcher.max_text_length:
            text = text[:StealthFetcher.max_text_length] + "\n\n... [截斷]"

        return {
            "ok": True, "url": getattr(page, 'url', ''),
            "content": text,
            "status_code": getattr(page, 'status', 0),
            "length": len(text), "fetcher": fetcher_label,
        }

    @staticmethod
    def _error_dict(url: str, error: str, fetcher_label: str = "stealth") -> dict:
        return {"ok": False, "url": url, "error": error,
                "content": "", "status_code": 0, "fetcher": fetcher_label}

    @classmethod
    def fetch_sync(cls, url: str, *,
                   headless: bool = None,
                   timeout: int = None,
                   wait_selector: str = None,
                   solve_cloudflare: bool = True,
                   extra_headers: dict = None,
                   proxy: str = None,
                   cdp_url: str = None,
                   real_chrome: bool = _HAS_REAL_CHROME,  # 🆕 auto-detect
                   ) -> dict:
        """同步抓取。

        :param url: 目標 URL
        :param headless: 無頭模式。CDP 模式下自動強制 False
        :param timeout: 超時毫秒
        :param solve_cloudflare: CF 自動破解（預設 True）
        :param cdp_url: CDP 地址 "http://127.0.0.1:9222"
                        連接已打開嘅真實 Chrome → 最強指紋 + 已登入態！
        :param real_chrome: 用本機真實 Chrome 而非 Chromium
        :param proxy: 代理 URL
        :param extra_headers: 額外 headers
        """
        from scrapling.fetchers import StealthyFetcher as ScraplingStealthy

        _timeout = timeout or cls.default_timeout
        _headless = headless if headless is not None else cls.headless

        # CDP = 真實 Chrome → headless 強制 False
        # 自動轉換 http:// → ws://（Scrapling 需要 WebSocket URL）
        if cdp_url:
            _headless = False
            if cdp_url.startswith("http://"):
                import urllib.request, json
                try:
                    cdp_info = json.loads(urllib.request.urlopen(
                        f"{cdp_url}/json/version").read())
                    cdp_url = cdp_info["webSocketDebuggerUrl"]
                except Exception:
                    pass  # 保持原 URL，可能本身就係 ws://

        kwargs: dict = {
            "headless": _headless, "timeout": _timeout,
            "solve_cloudflare": solve_cloudflare,
            "network_idle": True, "block_ads": True, "google_search": True,
            "real_chrome": real_chrome,
        }
        if cdp_url:
            kwargs["cdp_url"] = cdp_url
        if extra_headers:
            kwargs["extra_headers"] = extra_headers
        if proxy:
            kwargs["proxy"] = proxy
        if wait_selector:
            kwargs["wait_selector"] = wait_selector

        try:
            page = ScraplingStealthy.fetch(url, **kwargs)
            return cls._to_dict(page)
        except Exception as e:
            logger.error(f"[StealthFetcher] failed: {e}")
            return cls._error_dict(url, str(e))

    @classmethod
    async def fetch(cls, url: str, **kwargs) -> dict:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: cls.fetch_sync(url, **kwargs))

    @classmethod
    def session(cls, headless: bool = None, proxy: str = None,
                cdp_url: str = None, real_chrome: bool = False, **kwargs):
        """創建持久 Stealth Session。

        用法:
            async with StealthFetcher.session(cdp_url="http://127.0.0.1:9222") as s:
                r1 = s.fetch_sync("https://page1.com")
                r2 = s.fetch_sync("https://page2.com")
        """
        return _ScraplingSession(
            headless=headless if headless is not None else cls.headless,
            proxy=proxy, cdp_url=cdp_url, real_chrome=real_chrome, **kwargs)


class _ScraplingSession:
    """持久隱身瀏覽器 Session — 底層 Scrapling StealthySession。"""

    def __init__(self, headless: bool = True, proxy: str = None,
                 cdp_url: str = None, real_chrome: bool = False, **kwargs):
        self._headless = False if cdp_url else headless
        self._proxy = proxy
        self._cdp_url = cdp_url
        self._real_chrome = real_chrome
        self._kwargs = kwargs
        self._session = None

    def __enter__(self):
        from scrapling.fetchers import StealthySession
        self._session = StealthySession(
            headless=self._headless, proxy=self._proxy,
            cdp_url=self._cdp_url, real_chrome=self._real_chrome,
            solve_cloudflare=True, block_ads=True,
            **self._kwargs,
        )
        self._session.start()
        return self

    def __exit__(self, *args):
        if self._session:
            try: self._session.close()
            except Exception: pass

    async def __aenter__(self):
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(None, self.__enter__)

    async def __aexit__(self, *args):
        import asyncio
        await asyncio.get_event_loop().run_in_executor(None, self.__exit__, *args)

    def fetch_sync(self, url: str, **kwargs) -> dict:
        if not self._session:
            raise RuntimeError("Session not started")
        try:
            page = self._session.fetch(url, **kwargs)
            return StealthFetcher._to_dict(page, fetcher_label="stealth_session")
        except Exception as e:
            return StealthFetcher._error_dict(url, str(e), fetcher_label="stealth_session")

    async def fetch(self, url: str, **kwargs) -> dict:
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(None, self.fetch_sync, url, **kwargs)
