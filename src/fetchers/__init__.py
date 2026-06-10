#!/usr/bin/env python3
"""
Smart Agent Fetcher 架構 — 移植自 Scrapling 三層設計哲學

三層 Fetcher，每層內部全自動：
  LightFetcher   — 純 HTTP (curl_cffi TLS 偽裝 + 動態 headers + HTTP/3)
  StealthFetcher — 全副武裝隱身瀏覽器 (67 flags + CF繞過 + 廣告攔截 + 指紋保護)
  SmartFetcher   — 自動選擇 (先試 Light → 被封就升 Stealth)

用法：
  from src.fetchers import SmartFetcher
  result = await SmartFetcher.fetch(url)                           # auto 模式
  result = await SmartFetcher.fetch(url, mode="light")             # 輕量
  result = await SmartFetcher.fetch(url, mode="stealth")           # 全副武裝
"""

from src.fetchers.light import LightFetcher
from src.fetchers.stealth import StealthFetcher
from src.fetchers.smart import SmartFetcher

__all__ = ["LightFetcher", "StealthFetcher", "SmartFetcher"]
