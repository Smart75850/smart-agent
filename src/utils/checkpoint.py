#!/usr/bin/env python3
"""断点续爬 + 去重：SQLite 实现的 CheckpointManager。"""

import hashlib
import json
import sqlite3
import threading
from pathlib import Path


_CHECKPOINT_INSTANCE = None
_CHECKPOINT_LOCK = threading.Lock()


def get_checkpoint(db_path: str = None) -> "CheckpointManager":
    global _CHECKPOINT_INSTANCE
    if _CHECKPOINT_INSTANCE is None:
        with _CHECKPOINT_LOCK:
            if _CHECKPOINT_INSTANCE is None:
                _CHECKPOINT_INSTANCE = CheckpointManager(db_path)
    return _CHECKPOINT_INSTANCE


class CheckpointManager:
    """SQLite 持久化：任务进度 + 内容去重。"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path(__file__).resolve().parent.parent.parent / "output" / "checkpoint.db")
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    # ── connection ────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id        TEXT PRIMARY KEY,
                platform       TEXT NOT NULL,
                crawl_type     TEXT NOT NULL,
                keyword        TEXT,
                status         TEXT NOT NULL DEFAULT 'pending',
                collected_count INTEGER DEFAULT 0,
                current_page   INTEGER DEFAULT 0,
                error_msg      TEXT,
                created_at     TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                updated_at     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS dedup (
                item_hash  TEXT NOT NULL,
                platform   TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                PRIMARY KEY (item_hash, platform)
            );
        """)
        conn.commit()

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None

    # ── task management ──────────────────────────────────────

    @staticmethod
    def _task_id(platform: str, crawl_type: str, keyword: str) -> str:
        raw = f"{platform}:{crawl_type}:{keyword}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def task_exists(self, platform: str, crawl_type: str, keyword: str) -> bool:
        tid = self._task_id(platform, crawl_type, keyword)
        cur = self._get_conn().execute("SELECT 1 FROM tasks WHERE task_id=?", (tid,))
        return cur.fetchone() is not None

    def is_task_done(self, platform: str, crawl_type: str, keyword: str) -> bool:
        tid = self._task_id(platform, crawl_type, keyword)
        cur = self._get_conn().execute(
            "SELECT 1 FROM tasks WHERE task_id=? AND status='done'", (tid,)
        )
        return cur.fetchone() is not None

    def save_task(self, platform: str, crawl_type: str, keyword: str,
                  status: str = "pending", collected_count: int = 0,
                  current_page: int = 0, error_msg: str = None):
        tid = self._task_id(platform, crawl_type, keyword)
        self._get_conn().execute("""
            INSERT INTO tasks (task_id, platform, crawl_type, keyword, status, collected_count, current_page, error_msg)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(task_id) DO UPDATE SET
                status=excluded.status,
                collected_count=excluded.collected_count,
                current_page=excluded.current_page,
                error_msg=excluded.error_msg,
                updated_at=datetime('now','localtime')
        """, (tid, platform, crawl_type, keyword, status, collected_count, current_page, error_msg))
        self._get_conn().commit()

    def mark_done(self, platform: str, crawl_type: str, keyword: str,
                  collected_count: int = 0):
        tid = self._task_id(platform, crawl_type, keyword)
        self._get_conn().execute("""
            UPDATE tasks SET status='done', collected_count=?, updated_at=datetime('now','localtime')
            WHERE task_id=?
        """, (collected_count, tid))
        self._get_conn().commit()

    def mark_failed(self, platform: str, crawl_type: str, keyword: str,
                    error_msg: str = None):
        tid = self._task_id(platform, crawl_type, keyword)
        self._get_conn().execute("""
            UPDATE tasks SET status='failed', error_msg=?, updated_at=datetime('now','localtime')
            WHERE task_id=?
        """, (error_msg, tid))
        self._get_conn().commit()

    def get_pending_tasks(self) -> list[dict]:
        cur = self._get_conn().execute(
            "SELECT * FROM tasks WHERE status IN ('pending','failed') ORDER BY created_at"
        )
        return [dict(r) for r in cur.fetchall()]

    def get_all_tasks(self) -> list[dict]:
        cur = self._get_conn().execute("SELECT * FROM tasks ORDER BY created_at")
        return [dict(r) for r in cur.fetchall()]

    def clear_done_tasks(self):
        self._get_conn().execute("DELETE FROM tasks WHERE status='done'")
        self._get_conn().commit()

    # ── dedup ─────────────────────────────────────────────────

    @staticmethod
    def _make_hash(item: dict) -> str:
        serialized = json.dumps(item, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(serialized.encode()).hexdigest()

    def is_collected(self, item: dict, platform: str) -> bool:
        h = self._make_hash(item)
        cur = self._get_conn().execute(
            "SELECT 1 FROM dedup WHERE item_hash=? AND platform=?", (h, platform)
        )
        return cur.fetchone() is not None

    def mark_collected(self, item: dict, platform: str):
        h = self._make_hash(item)
        self._get_conn().execute(
            "INSERT OR IGNORE INTO dedup (item_hash, platform) VALUES (?,?)",
            (h, platform),
        )
        self._get_conn().commit()

    def mark_collected_batch(self, items: list[dict], platform: str):
        rows = [(self._make_hash(item), platform) for item in items]
        self._get_conn().executemany(
            "INSERT OR IGNORE INTO dedup (item_hash, platform) VALUES (?,?)", rows,
        )
        self._get_conn().commit()

    def filter_new_items(self, items: list[dict], platform: str) -> list[dict]:
        """返回 items 中尚未收录的新条目（已自动 mark_collected_batch）。"""
        new_items = []
        rows = []
        for item in items:
            h = self._make_hash(item)
            cur = self._get_conn().execute(
                "SELECT 1 FROM dedup WHERE item_hash=? AND platform=?", (h, platform)
            )
            if cur.fetchone() is None:
                new_items.append(item)
                rows.append((h, platform))

        if rows:
            self._get_conn().executemany(
                "INSERT OR IGNORE INTO dedup (item_hash, platform) VALUES (?,?)", rows,
            )
            self._get_conn().commit()

        return new_items
