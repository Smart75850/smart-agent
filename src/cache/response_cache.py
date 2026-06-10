#!/usr/bin/env python3
"""
開發模式響應緩存 — 移植自 Scrapling spiders/cache.py

功能：
  - 首次請求緩存響應到磁盤
  - 後續請求直接讀取緩存（唔打目標服務器）
  - 加速 parse() 邏輯開發迭代
  - 按 URL SHA256 去重

用法:
  from src.cache.response_cache import ResponseCache

  cache = ResponseCache("./crawl_cache")
  # 開發模式
  response = await cache.get_or_fetch(url, fetch_func)
  # 第一次 → 真正請求 + 緩存
  # 第二次 → 讀取緩存（唔打 server）
"""

import json
import time
from hashlib import sha256
from pathlib import Path
from typing import Callable, Optional


class ResponseCache:
    """開發模式響應緩存 — 加速 adapter 開發迭代。"""

    def __init__(self, cache_dir: str = "./.scrapling_cache"):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._index_file = self._cache_dir / "_index.json"
        self._index: dict[str, dict] = self._load_index()
        self._enabled = True

    def _load_index(self) -> dict:
        if self._index_file.exists():
            try:
                return json.loads(self._index_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_index(self):
        self._index_file.write_text(json.dumps(self._index, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _url_key(url: str) -> str:
        return sha256(url.encode()).hexdigest()[:16]

    def _cache_path(self, url_key: str) -> Path:
        return self._cache_dir / f"{url_key}.json"

    def get(self, url: str) -> Optional[dict]:
        """從緩存讀取響應。

        :param url: 請求 URL
        :return: 緩存嘅響應 dict，未命中返回 None
        """
        if not self._enabled:
            return None

        key = self._url_key(url)
        path = self._cache_path(key)

        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data
            except Exception:
                pass

        return None

    def set(self, url: str, response: dict):
        """保存響應到緩存。

        :param url: 請求 URL
        :param response: 響應 dict
        """
        key = self._url_key(url)
        path = self._cache_path(key)

        cache_entry = {
            "url": url,
            "cached_at": time.time(),
            "response": response,
        }

        path.write_text(json.dumps(cache_entry, ensure_ascii=False, indent=2), encoding="utf-8")

        self._index[key] = {
            "url": url,
            "cached_at": time.time(),
            "size": path.stat().st_size,
        }
        self._save_index()

    async def get_or_fetch(self, url: str, fetch_func: Callable) -> dict:
        """獲取響應（緩存優先）。

        開發模式流程：
          1. 檢查緩存 → 有就返回
          2. 冇緩存 → 真正請求 → 保存到緩存 → 返回

        :param url: 請求 URL
        :param fetch_func: 異步請求函數 async fn() -> dict
        :return: 響應 dict（帶 _cached 標記）
        """
        # 先查緩存
        cached = self.get(url)
        if cached:
            from src.utils.logger import logger
            logger.debug(f"[Cache] HIT: {url[:60]}")
            cached["_cached"] = True
            return cached

        # 緩存未命中 → 真正請求
        result = await fetch_func()
        if result and result.get("ok"):
            self.set(url, result)

        return result

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value

    @property
    def stats(self) -> dict:
        return {
            "cache_dir": str(self._cache_dir),
            "entries": len(self._index),
            "total_size_mb": sum(
                self._cache_path(k).stat().st_size
                for k in self._index
                if self._cache_path(k).exists()
            ) / 1024 / 1024,
        }

    def clear(self):
        """清空緩存"""
        for key in list(self._index.keys()):
            path = self._cache_path(key)
            if path.exists():
                path.unlink()
        self._index.clear()
        if self._index_file.exists():
            self._index_file.unlink()
