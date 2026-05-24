from .json_store import JSONStore
from .csv_store import CSVStore

_stores = {
    "json": JSONStore,
    "csv": CSVStore,
    "jsonl": None,
    "excel": None,
    "sqlite": None,
    "mysql": None,
}

# backend → (module_suffix, class_name)
_LAZY_MAP = {
    "jsonl":  (".jsonl_store",  "JSONLStore"),
    "excel":  (".excel_store",  "ExcelStore"),
    "sqlite": (".sqlite_store", "SQLiteStore"),
    "mysql":  (".mysql_store",  "MySQLStore"),
}


def get_store(backend: str = "json"):
    cls = _stores.get(backend)
    if cls is None:
        entry = _LAZY_MAP.get(backend)
        if entry:
            import importlib
            mod = importlib.import_module(entry[0], "store")
            cls = getattr(mod, entry[1])
            _stores[backend] = cls
        else:
            raise ValueError(f"不支持的儲存後端: {backend}")
    if cls is None:
        raise ValueError(f"不支持的儲存後端: {backend}")
    # MySQLStore 要傳 config
    if backend == "mysql":
        from config.settings import settings
        return cls(
            host=settings.MYSQL_HOST, port=settings.MYSQL_PORT,
            user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
            database=settings.MYSQL_DATABASE,
        )
    return cls()
