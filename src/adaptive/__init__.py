#!/usr/bin/env python3
"""
Smart Agent 自適應解析引擎 — 移植自 Scrapling 核心算法

三層架構：
  storage.py    — SQLite 元素指紋持久化（按域名隔離）
  fingerprint.py — 元素特徵提取 + 相似度計算
  relocator.py  — 元素重定位引擎（XPath 三層 + find_similar）

用法：
  from src.adaptive import AdaptiveEngine
  engine = AdaptiveEngine()
  engine.save(element, "product-card")     # 保存指紋
  found = engine.relocate(html, "product-card")  # 網站改版後搵返
"""

from src.adaptive.storage import FingerprintStore
from src.adaptive.relocator import Relocator

__all__ = ["FingerprintStore", "Relocator"]
