#!/usr/bin/env python3
from __future__ import annotations
"""
反反爬自動升級引擎 — 檢測封鎖 → 自動逐級加強反反爬措施

升級階梯（由輕到重）：
  Level 0 → 基礎 Stealth（67 flags + 動態 headers + DNS 防洩漏）         [預設常開]
  Level 1 → + 資源攔截（廣告域名 + 非必要資源）                            [自動]
  Level 2 → + Cloudflare Solver（Turnstile/Interstitial 自動化解決）      [自動]
  Level 3 → + Proxy 輪換（換 IP 重試）                                    [自動]
  Level 4 → + CDP 真實瀏覽器（完整指紋，人類行為模擬）                     [自動]

檢測信號：
  - HTTP Status: 403, 503, 521, 502, 429
  - Cloudflare: <title>Just a moment...</title>
  - 空洞響應: content length < 100 chars
  - 超時/連接錯誤
  - CAPTCHA 關鍵詞

用法：
  from src.utils.anti_bot_escalator import AntiBotEscalator
  escalator = AntiBotEscalator()
  result = await escalator.fetch_with_escalation(url, fetch_func)
"""

import asyncio
import os
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Awaitable

from config.settings import settings
from src.utils.logger import logger


class EscalationLevel(IntEnum):
    """反反爬升級等級"""
    STEALTH_BASE = 0       # 基礎隱身（flags + headers + DNS）
    RESOURCE_BLOCKING = 1  # + 資源/廣告攔截
    CLOUDFLARE_SOLVER = 2  # + CF Turnstile 破解
    PROXY_ROTATION = 3     # + Proxy 輪換
    CDP_BROWSER = 4        # + 真實 Chrome（人類行為）


@dataclass
class EscalationState:
    """當前升級狀態"""
    level: EscalationLevel = EscalationLevel.STEALTH_BASE
    attempt_count: int = 0
    proxy_index: int = 0
    last_error: str = ""
    blocked_history: list[str] = field(default_factory=list)


# 封鎖檢測特徵
BLOCKED_STATUS_CODES = frozenset({401, 403, 407, 429, 444, 500, 502, 503, 504, 521})
CF_TITLE_MARKER = "<title>Just a moment...</title>"
CF_VERIFY_MARKERS = [
    "verify you are human",
    "checking your browser",
    "cf-browser-verify",
    "cf_chl_opt",
    "challenge-platform",
    "turnstile",
]
CAPTCHA_MARKERS = [
    "captcha",
    "recaptcha",
    "hcaptcha",
    "are you a robot",
]


class AntiBotEscalator:
    """反反爬自動升級器。

    當請求被網站封鎖時，自動按照升級階梯（Level 0→4）逐級加強反反爬措施，
    直到請求成功或用盡所有級別。

    設計原則：
      - 預設只用 Level 0（最快、最安全）
      - 遇到封鎖才自動升級
      - 每次升級前等待遞增 delay（避免觸發 rate limit）
      - 記錄封鎖歷史供 ACI 記憶系統學習
    """

    def __init__(self, max_level: EscalationLevel = EscalationLevel.CDP_BROWSER):
        """
        :param max_level: 最高升級級別（預設 Level 4 = CDP）
        """
        self._max_level = max_level
        self._state = EscalationState()
        # 升級延遲（指數增長：1s → 2s → 4s → 8s）
        self._base_delay = 1.0

    @property
    def current_level(self) -> EscalationLevel:
        return self._state.level

    @property
    def state(self) -> EscalationState:
        return self._state

    def reset(self):
        """重置升級狀態（每次新請求開始時調用）"""
        self._state = EscalationState()

    @staticmethod
    def detect_blocking(response_text: str, status_code: int) -> str | None:
        """檢測響應是否被網站封鎖。

        :param response_text: 頁面文本內容
        :param status_code: HTTP 狀態碼
        :return: 封鎖類型描述（str）或 None（未被封）
        """
        # 1. 狀態碼檢測
        if status_code in BLOCKED_STATUS_CODES:
            return f"HTTP {status_code}"

        # 2. Cloudflare 檢測
        if CF_TITLE_MARKER in response_text:
            return "Cloudflare Interstitial"

        for marker in CF_VERIFY_MARKERS:
            if marker in response_text.lower():
                return f"Cloudflare Challenge ({marker})"

        # 3. CAPTCHA 檢測
        for marker in CAPTCHA_MARKERS:
            if marker in response_text.lower():
                return f"CAPTCHA ({marker})"

        # 4. 空洞響應（可能被無聲攔截）
        cleaned = response_text.strip()
        if len(cleaned) < 100 and status_code == 200:
            return f"Empty response ({len(cleaned)} chars)"

        return None

    def get_escalation_config(self, level: EscalationLevel) -> dict:
        """根據升級級別返回環境變數配置。

        :param level: 當前升級級別
        :return: 環境變數 dict（可直接 os.environ.update()）
        """
        configs = {
            EscalationLevel.STEALTH_BASE: {
                "BROWSER_STEALTH": "true",
                "DISABLE_RESOURCES": "false",
                "BLOCK_ADS": "false",
                "SOLVE_CLOUDFLARE": "false",
            },
            EscalationLevel.RESOURCE_BLOCKING: {
                "DISABLE_RESOURCES": "true",
                "BLOCK_ADS": "true",
                "SOLVE_CLOUDFLARE": "false",
            },
            EscalationLevel.CLOUDFLARE_SOLVER: {
                "DISABLE_RESOURCES": "true",
                "BLOCK_ADS": "true",
                "SOLVE_CLOUDFLARE": "true",
            },
            EscalationLevel.PROXY_ROTATION: {
                "DISABLE_RESOURCES": "true",
                "BLOCK_ADS": "true",
                "SOLVE_CLOUDFLARE": "true",
                "PROXY_ENABLED": "true",
            },
            EscalationLevel.CDP_BROWSER: {
                "BROWSER_ENGINE": "cdp",
                "DISABLE_RESOURCES": "true",
                "BLOCK_ADS": "true",
                "SOLVE_CLOUDFLARE": "true",
                "PROXY_ENABLED": "true",
            },
        }
        return configs.get(level, configs[EscalationLevel.STEALTH_BASE])

    def apply_level(self, level: EscalationLevel):
        """應用指定升級級別（設置環境變數）。

        :param level: 升級級別
        """
        config = self.get_escalation_config(level)
        os.environ.update(config)
        self._state.level = level
        logger.info(f"[Escalator] Level ↑ {level.name} ({level.value}) — {config}")

    async def escalate(self, error_reason: str) -> EscalationLevel | None:
        """升級到下一個級別。

        :param error_reason: 封鎖原因（用於日誌）
        :return: 新級別，如果已達上限則返回 None
        """
        if self._state.level >= self._max_level:
            logger.error(f"[Escalator] 已達最高級別 {self._state.level.name}，無法繼續升級")
            return None

        next_level = EscalationLevel(self._state.level.value + 1)
        self._state.blocked_history.append(
            f"L{self._state.level.value}: {error_reason}"
        )

        # 指數退避延遲
        delay = self._base_delay * (2 ** self._state.level.value)
        logger.warning(
            f"[Escalator] 封鎖檢測: {error_reason} → 升級到 {next_level.name} "
            f"(等待 {delay:.1f}s)"
        )
        await asyncio.sleep(delay)

        self.apply_level(next_level)
        self._state.attempt_count += 1
        return next_level

    async def fetch_with_escalation(
        self,
        url: str,
        fetch_func: Callable[[], Awaitable[dict]],
        max_total_attempts: int = 6,
    ) -> dict:
        """執行帶自動升級嘅請求。

        請求失敗（被封鎖）→ 自動升級 → 重試 → 直到成功或用盡級別。

        :param url: 目標 URL
        :param fetch_func: 請求函數（async callable，返回 dict with 'status'/'text' keys）
        :param max_total_attempts: 最大總嘗試次數（包括所有級別的重試）
        :return: 請求結果 dict
        """
        self.reset()
        self.apply_level(EscalationLevel.STEALTH_BASE)

        last_result = None

        for attempt in range(max_total_attempts):
            self._state.attempt_count = attempt + 1

            try:
                result = await fetch_func()
                last_result = result

                # 檢測是否被封鎖
                status = result.get("status", result.get("status_code", 0))
                text = result.get("text", result.get("content", ""))
                blocking_reason = self.detect_blocking(str(text), status)

                if blocking_reason is None:
                    # 成功！
                    if self._state.level > EscalationLevel.STEALTH_BASE:
                        logger.info(
                            f"[Escalator] 請求成功 (Level {self._state.level.name}, "
                            f"attempt {attempt + 1})"
                        )
                    return result

                # 被封鎖 → 升級
                logger.warning(f"[Escalator] 被封鎖: {blocking_reason} (attempt {attempt + 1})")
                new_level = await self.escalate(blocking_reason)

                if new_level is None:
                    # 已達上限
                    result["_blocked"] = True
                    result["_block_reason"] = blocking_reason
                    result["_escalation_history"] = self._state.blocked_history
                    return result

            except (asyncio.TimeoutError, ConnectionError, OSError) as e:
                error_type = type(e).__name__
                logger.warning(f"[Escalator] 連接錯誤: {error_type} (attempt {attempt + 1})")
                new_level = await self.escalate(f"Connection: {error_type}")

                if new_level is None:
                    return {
                        "ok": False,
                        "url": url,
                        "error": str(e),
                        "_escalation_history": self._state.blocked_history,
                    }

            except Exception as e:
                logger.error(f"[Escalator] 未預期錯誤: {type(e).__name__}: {e}")
                return {
                    "ok": False,
                    "url": url,
                    "error": f"{type(e).__name__}: {e}",
                    "_escalation_history": self._state.blocked_history,
                }

        # 用盡所有嘗試
        if last_result:
            last_result["_blocked"] = True
            last_result["_escalation_history"] = self._state.blocked_history
        return last_result or {
            "ok": False,
            "url": url,
            "error": "Max attempts exhausted",
            "_escalation_history": self._state.blocked_history,
        }


# 全局單例
escalator = AntiBotEscalator()
