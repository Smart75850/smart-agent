import json


class MySQLStore:
    """MySQL 儲存後端 — 可選，需安裝 mysql-connector-python。"""

    def __init__(self, host="localhost", port=3306, user="root", password="", database="smart_agent"):
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database

    def save(self, data: list[dict], output_dir: str, platform: str) -> str:
        import mysql.connector

        conn = mysql.connector.connect(
            host=self._host,
            port=self._port,
            user=self._user,
            password=self._password,
            database=self._database,
        )
        try:
            table = platform.replace("-", "_").replace(".", "_")
            if data:
                cols = list(data[0].keys())
                col_defs = ", ".join(f"`{c}` TEXT" for c in cols)
                conn.cursor().execute(f"CREATE TABLE IF NOT EXISTS `{table}` ({col_defs})")
                placeholders = ", ".join("%s" for _ in cols)
                col_names = ", ".join(f"`{c}`" for c in cols)
                sql = f"INSERT INTO `{table}` ({col_names}) VALUES ({placeholders})"
                for row in data:
                    values = [
                        json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
                        for v in row.values()
                    ]
                    conn.cursor().execute(sql, values)
            conn.commit()
        finally:
            conn.close()
        return f"mysql://{self._host}:{self._port}/{self._database}/{table}"
