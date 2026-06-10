#!/usr/bin/env python3
"""
SQLite 元素指紋持久化存儲 — 移植自 Scrapling core/storage.py

設計：
  - 按域名隔離存儲（不同網站嘅元素指紋互不干擾）
  - orjson 序列化（比標準 json 快 10 倍）
  - WAL 模式支持並發讀寫
  - UNIQUE (domain, identifier) 自動 upsert

用法：
  store = FingerprintStore()
  store.save("www.example.com", "product-card", {"tag": "div", "class": "product", ...})
  data = store.retrieve("www.example.com", "product-card")
"""

import sqlite3
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Optional, Any

try:
    import orjson
    def _dumps(obj): return orjson.dumps(obj)
    def _loads(data): return orjson.loads(data)
except ImportError:
    import json
    def _dumps(obj): return json.dumps(obj, ensure_ascii=False).encode()
    def _loads(data): return json.loads(data)


class FingerprintStore:
    """SQLite 元素指紋存儲 — 線程安全，支持並發。

    按域名隔離：每個網站嘅元素指紋分開存儲。
    自動 upsert：相同 (domain, identifier) 會覆蓋舊數據。
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path(__file__).resolve().parent.parent.parent / "output" / "adaptive_fingerprints.db")
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._conn: Any = None
        self._init_db()

    def _get_conn(self) -> Any:  # sqlite3.Connection
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fingerprints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                identifier TEXT NOT NULL,
                element_data TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE (domain, identifier)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fp_domain ON fingerprints(domain)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fp_ident ON fingerprints(identifier)")
        conn.commit()

    @staticmethod
    def domain_from_url(url: str) -> str:
        """從 URL 提取域名（用於隔離存儲）"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc or parsed.hostname or "default"
        except Exception:
            return url.lower().strip()

    def save(self, domain_or_url: str, identifier: str, element_data: dict) -> None:
        """保存元素指紋。

        :param domain_or_url: 域名或完整 URL（自動提取域名）
        :param identifier: 元素標識符（如 "product-card", "search-result"）
        :param element_data: 元素特徵 dict（tag, attrs, text, depth, path...）
        """
        domain = self.domain_from_url(domain_or_url)
        if not identifier:
            identifier = sha256(_dumps(element_data)).hexdigest()[:12]

        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """INSERT OR REPLACE INTO fingerprints (domain, identifier, element_data)
                   VALUES (?, ?, ?)""",
                (domain, identifier, _dumps(element_data).decode() if isinstance(_dumps(element_data), bytes) else _dumps(element_data))
            )
            conn.commit()

    def retrieve(self, domain_or_url: str, identifier: str) -> Optional[dict]:
        """檢索已保存嘅元素指紋。

        :param domain_or_url: 域名或完整 URL
        :param identifier: 元素標識符
        :return: 元素特徵 dict，未找到返回 None
        """
        domain = self.domain_from_url(domain_or_url)

        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT element_data FROM fingerprints WHERE domain = ? AND identifier = ?",
                (domain, identifier)
            ).fetchone()

        if row:
            raw = row[0]
            return _loads(raw.encode()) if isinstance(raw, str) else _loads(raw)
        return None

    def list_identifiers(self, domain_or_url: str) -> list[str]:
        """列出某域名下所有已保存嘅元素標識符。

        :param domain_or_url: 域名或完整 URL
        :return: 標識符列表
        """
        domain = self.domain_from_url(domain_or_url)

        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT identifier FROM fingerprints WHERE domain = ? ORDER BY created_at DESC",
                (domain,)
            ).fetchall()

        return [r[0] for r in rows]

    def delete(self, domain_or_url: str, identifier: str) -> bool:
        """刪除指定元素指紋。

        :return: True 如果成功刪除
        """
        domain = self.domain_from_url(domain_or_url)

        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "DELETE FROM fingerprints WHERE domain = ? AND identifier = ?",
                (domain, identifier)
            )
            conn.commit()
            return cursor.rowcount > 0

    def stats(self) -> dict:
        """儲存統計"""
        with self._lock:
            conn = self._get_conn()
            total = conn.execute("SELECT COUNT(*) FROM fingerprints").fetchone()[0]
            domains = conn.execute(
                "SELECT domain, COUNT(*) as cnt FROM fingerprints GROUP BY domain ORDER BY cnt DESC"
            ).fetchall()
        return {
            "total_fingerprints": total,
            "domains": [{"domain": r[0], "count": r[1]} for r in domains],
            "db_path": self._db_path,
        }

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


# 全局單例
fingerprint_store = FingerprintStore()
