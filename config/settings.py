from dataclasses import dataclass
from os import environ
from pathlib import Path

# 自动加载項目根目錄的 .env
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass


@dataclass
class Settings:
    # 瀏覽器
    BROWSER_ENGINE: str = "auto"   # auto / playwright / cdp / camoufox
    CDP_PORT: int = 9222
    MAX_CONCURRENT_SEARCHES: int = 3  # 并发搜索上限
    PAGE_TIMEOUT: int = 30000
    SLEEP_AFTER_LOAD: int = 8            # SPA 等待秒數

    # Camoufox (Firefox 反檢測引擎)
    CAMOUFOX_HEADLESS: bool = False
    CAMOUFOX_HUMANIZE: bool = True
    CAMOUFOX_BLOCK_WEBRTC: bool = True
    CAMOUFOX_GEOIP: bool = True
    CAMOUFOX_OS: str = "windows"
    CAMOUFOX_LOCALE: str = "zh-CN"
    CAMOUFOX_SCREEN: str = ""
    CAMOUFOX_USER_DATA_DIR: str = ""

    # 代理
    PROXY_ENABLED: bool = False
    PROXY_URL: str = ""

    # Cookie
    COOKIE_DIR: str = "browser_data"

    # 儲存
    STORE_BACKEND: str = "json"
    OUTPUT_DIR: str = "output"

    # 下載
    DOWNLOAD_DIR: str = "downloads"
    DOWNLOAD_MAX_CONCURRENT: int = 3
    DOWNLOAD_MAX_FILE_MB: int = 500

    # ── SignSrv 签名服务 ──
    SIGN_SRV_ENABLED: bool = True
    SIGN_SRV_PORT: int = 18501
    SIGN_SRV_TIMEOUT: int = 10

    # ── JS 收割 ──
    HARVEST_ENABLED: bool = True
    HARVEST_INTERVAL_HOURS: int = 6
    HARVEST_ON_STARTUP: bool = False

    # ── 平台签名开关 ──
    SIGN_PLATFORM_ENABLED: str = "douyin,bilibili"

    # LangGraph
    LANGGRAPH_CHECKPOINT_DB: str = "output/langgraph_checkpoint.db"

    # Memory (RAG / 跨任务 recall) — 源：高强文书第 6/13/16 章
    MEMORY_SAVE_ENABLED: bool = False          # 默认关，避免 silent overhead
    MEMORY_CHROMA_PATH: str = "output/chroma"  # Chroma 持久化路径
    MEMORY_EMBED_MODEL: str = "BAAI/bge-small-zh-v1.5"  # sentence-transformers model

    # LLM (Doubao) — 相容舊 config
    LLM_API_KEY: str = ""
    LLM_API_URL: str = ""
    LLM_MODEL: str = "doubao-pro-32k"

    # DeepSeek V4 Flash — Agent LLM 後端
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # QWEN-VL (通义千问视觉模型) — 视频分析
    QWEN_API_KEY: str = ""
    QWEN_API_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL: str = "qwen-vl-max"

    # Canva — 模板搜索 (Phase 2)
    CANVA_API_KEY: str = ""

    # MySQL（可選後端）
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "smart_agent"

    @classmethod
    def from_env(cls) -> "Settings":
        """從環境變數讀取設定，override 預設值。"""
        return cls(
            BROWSER_ENGINE=environ.get("BROWSER_ENGINE", "auto"),
            CDP_PORT=int(environ.get("CDP_PORT", "9222")),
            PAGE_TIMEOUT=int(environ.get("PAGE_TIMEOUT", "30000")),
            SLEEP_AFTER_LOAD=int(environ.get("SLEEP_AFTER_LOAD", "8")),
            PROXY_ENABLED=environ.get("PROXY_ENABLED", "false").lower() == "true",
            PROXY_URL=environ.get("PROXY_URL", ""),
            COOKIE_DIR=environ.get("COOKIE_DIR", "browser_data"),
            STORE_BACKEND=environ.get("STORE_BACKEND", "json"),
            OUTPUT_DIR=environ.get("OUTPUT_DIR", "output"),
            DOWNLOAD_DIR=environ.get("DOWNLOAD_DIR", "downloads"),
            DOWNLOAD_MAX_CONCURRENT=int(environ.get("DOWNLOAD_MAX_CONCURRENT", "3")),
            DOWNLOAD_MAX_FILE_MB=int(environ.get("DOWNLOAD_MAX_FILE_MB", "500")),
            MYSQL_HOST=environ.get("MYSQL_HOST", "localhost"),
            MYSQL_PORT=int(environ.get("MYSQL_PORT", "3306")),
            MYSQL_USER=environ.get("MYSQL_USER", "root"),
            MYSQL_PASSWORD=environ.get("MYSQL_PASSWORD", ""),
            MYSQL_DATABASE=environ.get("MYSQL_DATABASE", "smart_agent"),
            LANGGRAPH_CHECKPOINT_DB=environ.get("LANGGRAPH_CHECKPOINT_DB", "output/langgraph_checkpoint.db"),
            MEMORY_SAVE_ENABLED=environ.get("MEMORY_SAVE_ENABLED", "false").lower() == "true",
            MEMORY_CHROMA_PATH=environ.get("MEMORY_CHROMA_PATH", "output/chroma"),
            MEMORY_EMBED_MODEL=environ.get("MEMORY_EMBED_MODEL", "BAAI/bge-small-zh-v1.5"),
            # SignSrv
            SIGN_SRV_ENABLED=environ.get("SIGN_SRV_ENABLED", "true").lower() == "true",
            SIGN_SRV_PORT=int(environ.get("SIGN_SRV_PORT", "18501")),
            SIGN_SRV_TIMEOUT=int(environ.get("SIGN_SRV_TIMEOUT", "10")),
            HARVEST_ENABLED=environ.get("HARVEST_ENABLED", "true").lower() == "true",
            HARVEST_INTERVAL_HOURS=int(environ.get("HARVEST_INTERVAL_HOURS", "6")),
            HARVEST_ON_STARTUP=environ.get("HARVEST_ON_STARTUP", "false").lower() == "true",
            SIGN_PLATFORM_ENABLED=environ.get("SIGN_PLATFORM_ENABLED", "douyin,bilibili"),
            LLM_API_KEY=environ.get("LLM_API_KEY", ""),
            LLM_API_URL=environ.get("LLM_API_URL", ""),
            LLM_MODEL=environ.get("LLM_MODEL", "doubao-pro-32k"),
            DEEPSEEK_API_KEY=environ.get("DEEPSEEK_API_KEY", ""),
            DEEPSEEK_API_URL=environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/v1"),
            DEEPSEEK_MODEL=environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            QWEN_API_KEY=environ.get("QWEN_API_KEY", ""),
            QWEN_API_URL=environ.get("QWEN_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            QWEN_MODEL=environ.get("QWEN_MODEL", "qwen-vl-max"),
            CANVA_API_KEY=environ.get("CANVA_API_KEY", ""),
            CAMOUFOX_HEADLESS=environ.get("CAMOUFOX_HEADLESS", "false").lower() == "true",
            CAMOUFOX_HUMANIZE=environ.get("CAMOUFOX_HUMANIZE", "true").lower() != "false",
            CAMOUFOX_BLOCK_WEBRTC=environ.get("CAMOUFOX_BLOCK_WEBRTC", "true").lower() != "false",
            CAMOUFOX_GEOIP=environ.get("CAMOUFOX_GEOIP", "true").lower() != "false",
            CAMOUFOX_OS=environ.get("CAMOUFOX_OS", "windows"),
            CAMOUFOX_LOCALE=environ.get("CAMOUFOX_LOCALE", "zh-CN"),
            CAMOUFOX_SCREEN=environ.get("CAMOUFOX_SCREEN", ""),
            CAMOUFOX_USER_DATA_DIR=environ.get("CAMOUFOX_USER_DATA_DIR", ""),
        )


# 全局單例
settings = Settings.from_env()
