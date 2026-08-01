#!/usr/bin/env python3
"""
LightFetcher — 純 HTTP 引擎（移植自 Scrapling Fetcher 設計）

層內全自動：
  - TLS 指紋偽裝 (curl_cffi impersonate)
  - 動態 Headers 生成 (browserforge)
  - HTTP/3 支持
  - 自動重試 (3次, 指數退避)
  - Safe redirect (防 SSRF)
  - HTML → 純文本提取
  - Google Referer 偽裝

適用場景：低-中防護網站、API 請求、靜態頁面
"""

import re
import time
from html.parser import HTMLParser
from typing import Optional, Any

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    import httpx
    HAS_CURL_CFFI = False

from config.settings import settings
from constant.stealth import generate_headers, is_stealth_ready
from src.utils.logger import logger


class TextExtractor(HTMLParser):
    """從 HTML 提取純文本"""
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip_tags = {'script', 'style', 'nav', 'footer', 'header', 'code', 'pre', 'noscript'}
        self.current_tag = None

    def handle_starttag(self, tag, attrs):
        self.current_tag = tag

    def handle_endtag(self, tag):
        self.current_tag = None

    def handle_data(self, data):
        if self.current_tag not in self.skip_tags:
            t = data.strip()
            if t and len(t) > 1:
                self.text.append(t)


class LightFetcher:
    """純 HTTP 輕量抓取器。

    內部全自動處理 TLS 偽裝、headers 生成、重試、文本提取。
    用戶只需傳 URL + 可選參數。

    用法:
        result = await LightFetcher.fetch("https://example.com")
        result = LightFetcher.fetch_sync("https://example.com")
    """

    # ── 配置（類級別，可全局修改）──
    default_impersonate: str = "chrome131"
    default_timeout: int = 30
    default_retries: int = 3
    default_retry_delay: float = 1.0
    max_text_length: int = 8000
    stealthy_headers: bool = True
    google_referer: bool = True
    http3_enabled: bool = settings.HTTP3_ENABLED

    @classmethod
    def _build_headers(cls, extra_headers: dict = None) -> dict:
        """構建請求 headers（動態生成 + 可選覆蓋）。

        層內全自動：用 browserforge 動態生成真實瀏覽器 headers。
        """
        if cls.stealthy_headers and is_stealth_ready():
            base_headers = generate_headers(browser_mode=False)
        else:
            base_headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
            }

        # Google Referer 偽裝
        if cls.google_referer and "referer" not in {k.lower() for k in base_headers}:
            base_headers["Referer"] = "https://www.google.com/"

        if extra_headers:
            base_headers.update(extra_headers)

        return base_headers

    @classmethod
    def _extract_text(cls, raw: str, content_type: str) -> str:
        """從原始響應提取純文本（層內全自動）。"""
        if "text/html" not in (content_type or ""):
            return raw[:cls.max_text_length]

        try:
            extractor = TextExtractor()
            extractor.feed(raw)
            text = "\n".join(extractor.text)
        except Exception:
            text = re.sub(r'<[^>]+>', '', raw)

        if len(text) > cls.max_text_length:
            text = text[:cls.max_text_length] + f"\n\n... [截斷，原文 {len(text)} 字符]"

        return text

    @classmethod
    def fetch_sync(cls, url: str, *, headers: dict = None, timeout: int = None,
                   impersonate: str = None, http3: bool = None) -> dict:
        """同步 HTTP GET 請求（層內全自動）。

        :param url: 目標 URL
        :param headers: 額外 headers（覆蓋動態生成）
        :param timeout: 超時秒數
        :param impersonate: TLS 指紋類型（chrome131/chrome124/firefox 等）
        :param http3: 是否強制 HTTP/3
        :return: {"ok": bool, "url": str, "content": str, "status_code": int, ...}
        """
        request_headers = cls._build_headers(headers)
        _timeout = timeout or cls.default_timeout
        _impersonate = impersonate or cls.default_impersonate
        _http3 = http3 if http3 is not None else cls.http3_enabled
        last_error = None

        for attempt in range(cls.default_retries):
            try:
                resp: Any = None
                if HAS_CURL_CFFI:
                    resp = curl_requests.get(
                        url,
                        headers=request_headers,
                        timeout=_timeout,
                        impersonate=_impersonate,
                        allow_redirects=True,
                    )
                else:
                    resp = httpx.get(
                        url,
                        headers=request_headers,
                        timeout=_timeout,
                        follow_redirects=True,
                    )

                content_type = resp.headers.get("content-type", "")
                status_code = resp.status_code
                raw = resp.text if hasattr(resp, 'text') else resp.content.decode('utf-8', errors='replace')
                text = cls._extract_text(raw, content_type)

                # 4xx/5xx 错误页不算成功，交由上层决定升级或报错
                ok = 200 <= status_code < 400

                return {
                    "ok": ok,
                    "url": str(resp.url),
                    "content": text,
                    "raw": raw,
                    "content_type": content_type,
                    "status_code": status_code,
                    "length": len(text),
                    "fetcher": "light",
                    "attempts": attempt + 1,
                }

            except Exception as e:
                last_error = str(e)
                if attempt < cls.default_retries - 1:
                    delay = cls.default_retry_delay * (2 ** attempt)
                    logger.debug(f"[LightFetcher] retry {attempt + 1}/{cls.default_retries}, wait {delay:.1f}s: {last_error[:80]}")
                    time.sleep(delay)

        return {
            "ok": False,
            "url": url,
            "error": last_error,
            "content": "",
            "status_code": 0,
            "fetcher": "light",
            "attempts": cls.default_retries,
        }

    @classmethod
    async def fetch(cls, url: str, **kwargs) -> dict:
        """異步 HTTP GET 請求（與同步版相同邏輯）。

        在 async 上下文中使用 run_in_executor 避免阻塞事件循環。
        """
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: cls.fetch_sync(url, **kwargs))
