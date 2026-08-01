import json
import re
import sqlite3
from pathlib import Path
from typing import Any

# 标识符净化：只允许字母/数字/下划线，防 SQL 标识符注入（表名/列名来自爬取数据的键）
_IDENT_RE = re.compile(r"[^A-Za-z0-9_]")


def _safe_ident(s: str) -> str:
    cleaned = _IDENT_RE.sub("_", str(s))[:64] or "_"
    return cleaned


class SQLiteStore:
    """SQLite 儲存後端 — 自動建 table、append、dict key 做欄位。"""

    def __init__(self, db_path: str = "output/smart_agent.db"):
        self._db_path = db_path

    def save(self, data: list[dict], output_dir: str, platform: str) -> str:
        db_path = Path(output_dir) / "smart_agent.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        try:
            table = _safe_ident(platform)
            if data:
                cols = list(dict.fromkeys(_safe_ident(c) for c in data[0].keys()))
                col_defs = ", ".join(f'"{c}" TEXT' for c in cols)
                conn.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({col_defs})')
                col_names = ", ".join(f'"{c}"' for c in cols)
                placeholders = ", ".join("?" for _ in cols)
                sql = f'INSERT INTO "{table}" ({col_names}) VALUES ({placeholders})'
                for row in data:
                    values = [
                        json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
                        for v in row.values()
                    ]
                    conn.execute(sql, values)
            conn.commit()
        finally:
            conn.close()
        return str(db_path)
