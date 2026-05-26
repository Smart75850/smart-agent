from dataclasses import dataclass
from os import environ


@dataclass
class Settings:
    # 瀏覽器
    BROWSER_ENGINE: str = "playwright"   # playwright / cdp / camoufox
    CDP_PORT: int = 9222
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

    # LangGraph
    LANGGRAPH_CHECKPOINT_DB: str = "output/langgraph_checkpoint.db"

    # LLM (Doubao) — 相容舊 config
    LLM_API_KEY: str = ""
    LLM_API_URL: str = ""
    LLM_MODEL: str = "doubao-pro-32k"

    # DeepSeek V4 Flash — Agent LLM 後端
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

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
            BROWSER_ENGINE=environ.get("BROWSER_ENGINE", "playwright"),
            CDP_PORT=int(environ.get("CDP_PORT", "9222")),
            PAGE_TIMEOUT=int(environ.get("PAGE_TIMEOUT", "30000")),
            SLEEP_AFTER_LOAD=int(environ.get("SLEEP_AFTER_LOAD", "8")),
            PROXY_ENABLED=environ.get("PROXY_ENABLED", "false").lower() == "true",
            PROXY_URL=environ.get("PROXY_URL", ""),
            COOKIE_DIR=environ.get("COOKIE_DIR", "browser_data"),
            STORE_BACKEND=environ.get("STORE_BACKEND", "json"),
            OUTPUT_DIR=environ.get("OUTPUT_DIR", "output"),
            MYSQL_HOST=environ.get("MYSQL_HOST", "localhost"),
            MYSQL_PORT=int(environ.get("MYSQL_PORT", "3306")),
            MYSQL_USER=environ.get("MYSQL_USER", "root"),
            MYSQL_PASSWORD=environ.get("MYSQL_PASSWORD", ""),
            MYSQL_DATABASE=environ.get("MYSQL_DATABASE", "smart_agent"),
            LANGGRAPH_CHECKPOINT_DB=environ.get("LANGGRAPH_CHECKPOINT_DB", "output/langgraph_checkpoint.db"),
            LLM_API_KEY=environ.get("LLM_API_KEY", ""),
            LLM_API_URL=environ.get("LLM_API_URL", ""),
            LLM_MODEL=environ.get("LLM_MODEL", "doubao-pro-32k"),
            DEEPSEEK_API_KEY=environ.get("DEEPSEEK_API_KEY", ""),
            DEEPSEEK_API_URL=environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/v1"),
            DEEPSEEK_MODEL=environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
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
