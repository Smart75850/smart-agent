#!/usr/bin/env python3
"""
SmartFetcher — 自動選擇最合適嘅 Fetcher 層級

三種模式：
  mode="auto"    → 先試 Light (HTTP) → 被封就自動升 Stealth (瀏覽器)
  mode="light"   → 只用 LightFetcher (HTTP)
  mode="stealth" → 只用 StealthFetcher (全副武裝)

設計哲學（移植自 Scrapling 分層思路）：
  - auto 模式：預設行為，遇到弱網站用輕量（快），遇到強網站自動升全副武裝
  - light/stealth 模式：進階用戶自選，類似 Scrapling 嘅 Fetcher vs StealthyFetcher

用法：
    from src.fetchers import SmartFetcher

    # 自動模式（推薦預設）
    result = await SmartFetcher.fetch("https://example.com")

    # 明知有 CF，直接全副武裝
    result = await SmartFetcher.fetch("https://cf-site.com", mode="stealth")

    # 靜態頁面，只要 HTTP
    result = await SmartFetcher.fetch("https://api.site.com", mode="light")
"""

from typing import Literal, Optional, Dict, Any

from src.fetchers.light import LightFetcher
from src.fetchers.stealth import StealthFetcher
from src.utils.anti_bot_escalator import AntiBotEscalator
from src.utils.logger import logger

FetchMode = Literal["auto", "light", "stealth"]


class SmartFetcher:
    """智能 Fetcher — 自動選擇 Light 或 Stealth。

    核心邏輯（auto 模式）：
      1. 先用 LightFetcher (HTTP) 試
      2. 檢測有冇被封鎖
      3. 冇封 → 返回（最快路徑）
      4. 被封 → 自動升級到 StealthFetcher（全副武裝瀏覽器）
      5. 返回結果

    light 模式 → 只用 HTTP（LightFetcher）
    stealth 模式 → 只用瀏覽器（StealthFetcher），層內全自動
    """

    @classmethod
    async def fetch(cls, url: str, *,
                    mode: FetchMode = "auto",
                    headers: Optional[dict] = None,
                    timeout: Optional[int] = None,
                    wait_selector: Optional[str] = None,
                    **kwargs) -> dict:
        """智能抓取 — 自動選擇並執行合適嘅 Fetcher。

        :param url: 目標 URL
        :param mode: "auto" | "light" | "stealth"
        :param headers: 額外 HTTP headers（僅 light 模式生效）
        :param timeout: 超時秒數
        :param wait_selector: CSS selector 等待（僅 stealth 模式生效）
        :param kwargs: 傳遞俾底層 Fetcher 嘅額外參數
        :return: {"ok": bool, "url": str, "content": str, "fetcher": "light"|"stealth", ...}
        """
        if mode == "light":
            return await cls._fetch_light(url, headers=headers, timeout=timeout, **kwargs)

        if mode == "stealth":
            return await cls._fetch_stealth(url, timeout=timeout,
                                            wait_selector=wait_selector, **kwargs)

        # mode == "auto": 先輕後重
        return await cls._fetch_auto(url, headers=headers, timeout=timeout,
                                     wait_selector=wait_selector, **kwargs)

    @classmethod
    async def _fetch_light(cls, url: str, **kwargs) -> dict:
        """純 HTTP 路徑 — 只傳遞 LightFetcher 接受嘅參數"""
        logger.debug(f"[SmartFetcher] light mode → {url}")
        light_kwargs = cls._filter_kwargs(kwargs, 'light')
        return await LightFetcher.fetch(url, **light_kwargs)

    @classmethod
    async def _fetch_stealth(cls, url: str, **kwargs) -> dict:
        """全副武裝瀏覽器路徑"""
        logger.debug(f"[SmartFetcher] stealth mode → {url}")
        stealth_kwargs = cls._filter_kwargs(kwargs, 'stealth')
        result = await StealthFetcher.fetch(url, **stealth_kwargs)
        result["fetcher"] = "stealth"
        return result

    @staticmethod
    def _filter_kwargs(kwargs: dict, target: str) -> dict:
        """過濾 kwargs，只保留目標 Fetcher 接受嘅參數"""
        if target == 'light':
            allowed = {"headers", "timeout", "impersonate", "http3"}
        else:  # stealth
            allowed = {"headless", "timeout", "wait_selector", "solve_cloudflare",
                       "page_action", "cookies", "cookie_domain", "proxy",
                       "extra_headers", "cdp_url", "real_chrome"}
        return {k: v for k, v in kwargs.items() if k in allowed}

    @classmethod
    async def _fetch_auto(cls, url: str, **kwargs) -> dict:
        """自動模式：先 Light → 檢測封鎖 → 必要時升級 Stealth"""
        logger.debug(f"[SmartFetcher] auto mode → {url}")

        light_kwargs = cls._filter_kwargs(kwargs, 'light')

        # ── Pass 1: LightFetcher (HTTP) ──
        light_result = await LightFetcher.fetch(url, **light_kwargs)

        stealth_kwargs = cls._filter_kwargs(kwargs, 'stealth')

        if not light_result["ok"]:
            # HTTP 完全失敗（網絡錯誤等）→ 直接升級 Stealth
            logger.info(f"[SmartFetcher] Light HTTP 失敗 → 升級 Stealth: {light_result.get('error', 'unknown')[:80]}")
            stealth_result = await StealthFetcher.fetch(url, **stealth_kwargs)
            stealth_result["fetcher"] = "auto:light_failed→stealth"
            return stealth_result

        # ── 檢測封鎖 ──
        content = light_result.get("content", "")
        status = light_result.get("status_code", 0)
        blocking_reason = AntiBotEscalator.detect_blocking(content, status)

        if blocking_reason is None:
            # 冇被封！直接返回 Light 結果（最快路徑）
            light_result["fetcher"] = "auto:light"
            return light_result

        # ── Pass 2: 被封 → 升級 StealthFetcher ──
        logger.info(f"[SmartFetcher] 檢測封鎖 ({blocking_reason}) → 升級 StealthFetcher")
        stealth_result = await StealthFetcher.fetch(url, **stealth_kwargs)

        if stealth_result["ok"]:
            stealth_result["fetcher"] = "auto:light_blocked→stealth"
            stealth_result["_auto_upgraded"] = True
            stealth_result["_block_reason"] = blocking_reason
            return stealth_result

        # Stealth 都失敗 → 返回最好嘅結果
        stealth_result["fetcher"] = "auto:both_failed"
        stealth_result["_block_reason"] = blocking_reason
        return stealth_result

    @classmethod
    async def session(cls, mode: FetchMode = "stealth", **kwargs):
        """創建持久 Session（目前僅支援 stealth 模式）。

        用法:
            async with SmartFetcher.session() as session:
                r1 = await session.fetch("https://page1.com")
                r2 = await session.fetch("https://page2.com")
        """
        if mode in ("stealth", "auto"):
            return StealthFetcher.session(**kwargs)
        raise ValueError("Session mode only supports 'stealth' or 'auto'")
