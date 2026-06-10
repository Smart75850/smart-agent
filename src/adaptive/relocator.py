#!/usr/bin/env python3
"""
元素重定位引擎 — 移植自 Scrapling parser.py find_similar + adaptive

核心算法（當網站改版後自動搵返元素）：

  1. 從 SQLite 讀取已保存嘅元素指紋
  2. 在新頁面 HTML 中遍歷所有候選元素
  3. 三層過濾：
     Layer 1: tag name 匹配（快速篩選）
     Layer 2: parent tag + depth 匹配（結構過濾）
     Layer 3: 相似度評分 (similarity_score) — 選最高分
  4. 返回匹配元素嘅新 CSS selector

用法:
  relocator = Relocator()
  new_selector = relocator.relocate(html, domain, "product-card")
  # → ".product-item"（網站改版後嘅新 selector）
"""

from typing import Optional

from src.adaptive.storage import FingerprintStore, fingerprint_store
from src.adaptive.fingerprint import extract_fingerprint, similarity_score, element_to_dict
from src.utils.logger import logger

# 默認相似度閾值（移植自 Scrapling）
DEFAULT_THRESHOLD = 0.2


class Relocator:
    """元素重定位引擎。

    當網站改版導致原有 CSS selector 失效時，自動搜索並定位目標元素。

    用法:
      relocator = Relocator()
      # 保存
      relocator.save("www.example.com", "product-card", element)
      # 改版後重定位
      result = relocator.relocate("www.example.com", "product-card", html_elements)
    """

    def __init__(self, store: FingerprintStore = None, threshold: float = DEFAULT_THRESHOLD):
        self._store = store or fingerprint_store
        self._threshold = threshold

    def save(self, domain_or_url: str, identifier: str, element) -> None:
        """保存元素指紋到 SQLite。

        :param domain_or_url: 域名或完整 URL
        :param identifier: 元素標識符（例如 "bilibili-video-card"）
        :param element: 元素對象（Playwright Locator / lxml Element / dict）
        """
        elem_dict = element_to_dict(element)
        fingerprint = extract_fingerprint(elem_dict)
        self._store.save(domain_or_url, identifier, fingerprint)
        logger.debug(f"[Relocator] Saved fingerprint '{identifier}' for {domain_or_url}")

    def relocate(self, domain_or_url: str, identifier: str,
                 candidates: list[dict], min_score: float = None) -> Optional[dict]:
        """在新頁面中重定位之前保存嘅元素。

        :param domain_or_url: 域名
        :param identifier: 元素標識符
        :param candidates: 新頁面中嘅候選元素列表（每個都係 dict）
        :param min_score: 最低相似度閾值（默認 0.2）
        :return: 最佳匹配元素 dict，或 None
        """
        saved_fp = self._store.retrieve(domain_or_url, identifier)
        if not saved_fp:
            logger.debug(f"[Relocator] No saved fingerprint for '{identifier}'")
            return None

        _min_score = min_score if min_score is not None else self._threshold

        best_match = None
        best_score = 0.0

        for candidate in candidates:
            cand_dict = element_to_dict(candidate)
            if not cand_dict.get("tag"):
                continue

            # Layer 1: tag name 快速篩選
            if cand_dict["tag"] != saved_fp.get("tag"):
                continue

            # Layer 2: depth 範圍檢查（容許 ±2）
            saved_depth = saved_fp.get("depth", 0)
            cand_depth = cand_dict.get("depth", 0)
            if saved_depth > 0 and abs(cand_depth - saved_depth) > 2:
                continue

            # Layer 3: 完整相似度計算
            cand_fp = extract_fingerprint(cand_dict)
            score = similarity_score(saved_fp, cand_fp)

            if score > best_score:
                best_score = score
                best_match = candidate

        if best_match and best_score >= _min_score:
            logger.debug(
                f"[Relocator] Relocated '{identifier}': score={best_score:.2f}, "
                f"tag={best_match.get('tag', '?')}"
            )
            return best_match

        logger.debug(f"[Relocator] No match for '{identifier}' (best_score={best_score:.2f} < {_min_score})")
        return None

    def relocate_with_selectors(self, domain_or_url: str, identifier: str,
                                candidates_by_selector: dict[str, list]) -> Optional[str]:
        """重定位並返回最佳匹配嘅 CSS selector。

        :param domain_or_url: 域名
        :param identifier: 元素標識符
        :param candidates_by_selector: {".new-selector": [elements], ...}
        :return: 最佳匹配嘅 CSS selector 字符串，或 None
        """
        all_candidates = []
        selector_map = {}  # candidate index → selector name

        for selector, elements in candidates_by_selector.items():
            for elem in elements:
                idx = len(all_candidates)
                all_candidates.append(elem)
                selector_map[idx] = selector

        match = self.relocate(domain_or_url, identifier, all_candidates)

        if match:
            # 找出匹配元素對應嘅 selector
            for idx, selector in selector_map.items():
                if idx < len(all_candidates) and all_candidates[idx] is match:
                    return selector
            # 如果直接對象匹配失敗，用相似度重找
            for idx, selector in selector_map.items():
                if idx < len(all_candidates):
                    cand_fp = extract_fingerprint(element_to_dict(all_candidates[idx]))
                    saved_fp = self._store.retrieve(domain_or_url, identifier)
                    if saved_fp and similarity_score(saved_fp, cand_fp) >= self._threshold:
                        return selector

        return None

    def save_from_selector(self, domain_or_url: str, identifier: str,
                           html: str, selector: str):
        """從 HTML + CSS selector 保存元素指紋（便捷方法）。

        :param domain_or_url: 域名
        :param identifier: 標識符
        :param html: 完整 HTML 字符串
        :param selector: CSS selector
        """
        try:
            from lxml import html as lxml_html
            tree = lxml_html.fromstring(html)
            elements = tree.cssselect(selector)
            if elements:
                self.save(domain_or_url, identifier, elements[0])
                logger.info(f"[Relocator] Auto-saved '{identifier}' from selector '{selector}'")
            else:
                logger.warning(f"[Relocator] No elements found for selector '{selector}'")
        except ImportError:
            logger.warning("[Relocator] lxml not installed, cannot parse HTML")
        except Exception as e:
            logger.error(f"[Relocator] save_from_selector failed: {e}")


# 全局單例
relocator = Relocator()
