from fastapi import APIRouter

from config.settings import settings
from constant.platform_registry import PLATFORMS as _PLATFORMS

router = APIRouter()


@router.get("/api/platforms")
async def list_platforms():
    return {"platforms": _PLATFORMS}


# 只暴露非敏感配置，绝不上送任何密钥/密码/token
_PUBLIC_CONFIG_FIELDS = (
    "BROWSER_ENGINE", "CDP_PORT", "MAX_CONCURRENT_SEARCHES", "PAGE_TIMEOUT",
    "SLEEP_AFTER_LOAD", "PROXY_ENABLED", "STORE_BACKEND", "OUTPUT_DIR",
    "DOWNLOAD_DIR", "DOWNLOAD_MAX_CONCURRENT", "DOWNLOAD_MAX_FILE_MB",
    "SIGN_SRV_ENABLED", "SIGN_SRV_PORT", "HARVEST_ENABLED",
    "HARVEST_INTERVAL_HOURS", "SIGN_PLATFORM_ENABLED",
    "LLM_API_URL", "LLM_MODEL", "DEEPSEEK_API_URL", "DEEPSEEK_MODEL",
    "QWEN_API_URL", "QWEN_MODEL",
    "CAMOUFOX_HEADLESS", "CAMOUFOX_HUMANIZE", "CAMOUFOX_BLOCK_WEBRTC",
    "CAMOUFOX_GEOIP", "CAMOUFOX_OS", "CAMOUFOX_LOCALE",
)


@router.get("/api/config")
async def get_config():
    # 白名单返回，任何含 KEY/PASSWORD/SECRET/TOKEN 的字段一律不暴露
    return {name: getattr(settings, name) for name in _PUBLIC_CONFIG_FIELDS if hasattr(settings, name)}
