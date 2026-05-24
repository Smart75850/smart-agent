"""
Cookie 管理 — Playwright / Camoufox 通用
開源版：基礎存儲+加載
Pro 版：多賬號 + 自動刷新 + 加密
"""
import json
from pathlib import Path


class CookieManager:
    """Cookie 持久化管理"""

    def __init__(self, storage_dir: str = "browser_data"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)

    def _path(self, platform: str) -> Path:
        return self.storage_dir / f"cookies_{platform}.json"

    async def save(self, platform: str, context) -> None:
        cookies = await context.cookies()
        with open(self._path(platform), "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)

    async def load(self, platform: str, context) -> bool:
        path = self._path(platform)
        if not path.exists():
            return False
        with open(path, encoding="utf-8") as f:
            cookies = json.load(f)
        await context.add_cookies(cookies)
        return True

    def has_cookies(self, platform: str) -> bool:
        return self._path(platform).exists()
