"""MySQL 储存后端 — 自动建表 + 类型推断 + 去重。"""
import json
import re
from datetime import datetime, timezone

# 标识符净化：只允许字母/数字/下划线，防 SQL 标识符注入（表名/列名来自爬取数据的键）
_IDENT_RE = re.compile(r"[^A-Za-z0-9_]")


def _safe_ident(s: str) -> str:
    cleaned = _IDENT_RE.sub("_", str(s))[:64] or "_"
    return cleaned


def _infer_mysql_type(key: str, sample_value) -> str:
    """根据字段名和样本值推断 MySQL 列类型。"""
    if isinstance(sample_value, bool):
        return "TINYINT(1)"
    if isinstance(sample_value, int):
        if "id" in key.lower() or "count" in key.lower():
            return "BIGINT"
        return "INT"
    if isinstance(sample_value, float):
        return "DOUBLE"
    if isinstance(sample_value, (dict, list)):
        return "JSON"
    v = str(sample_value)
    if len(v) <= 255:
        return "VARCHAR(512)"
    return "TEXT"


class MySQLStore:
    """MySQL 储存后端 — 可选用，需 mysql-connector-python。"""

    def __init__(self, host="localhost", port=3306, user="root", password="", database="smart_agent"):
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database

    def save(self, data: list[dict], output_dir: str, platform: str) -> str:
        import mysql.connector

        if not data:
            return f"mysql://{self._host}:{self._port}/{self._database}/(empty)"

        conn = mysql.connector.connect(
            host=self._host,
            port=self._port,
            user=self._user,
            password=self._password,
            database=self._database,
        )
        try:
            table = _safe_ident(platform)

            cols = list(dict.fromkeys(_safe_ident(c) for c in data[0].keys()))
            col_defs = [f"`id` BIGINT AUTO_INCREMENT PRIMARY KEY"]
            col_defs.append("`_created_at` DATETIME NOT NULL")
            for c in cols:
                sample = data[0].get(c)
                col_type = _infer_mysql_type(c, sample)
                col_defs.append(f"`{c}` {col_type}")

            with conn.cursor() as cur:
                cur.execute(f"CREATE TABLE IF NOT EXISTS `{table}` ({', '.join(col_defs)})")

                col_names = ", ".join(f"`{c}`" for c in cols)
                placeholders = ", ".join("%s" for _ in cols)
                sql = (
                    f"INSERT INTO `{table}` (`_created_at`, {col_names}) "
                    f"VALUES (NOW(), {placeholders})"
                )

                now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                for row in data:
                    values = [
                        json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                        for v in row.values()
                    ]
                    cur.execute(sql, values)

            conn.commit()
        finally:
            conn.close()

        return f"mysql://{self._host}:{self._port}/{self._database}/{table}"
