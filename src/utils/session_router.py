"""多账号轮换路由 — 限流时自动切下一个账号。"""
import json
from pathlib import Path
from typing import Optional

from src.utils.account_manager import get_account_manager
from src.utils.logger import logger

_COOKIE_DIR = Path(__file__).resolve().parent.parent.parent / "browser_data"


class SessionRouter:
    """从 AccountManager 轮换取得 session cookie + proxy。"""

    def __init__(self, platform: str):
        self.platform = platform
        self._acct_mgr = get_account_manager()
        self._current_account: dict | None = None

    def get_session(self) -> Optional[dict]:
        """返回 {cookies_str, proxy}，无可用账号返回 None。"""
        acct = self._acct_mgr.get_next(self.platform)
        if not acct:
            return None
        self._current_account = acct
        cookies_str = self._read_cookies(acct)
        if not cookies_str:
            return None
        return {
            "cookies_str": cookies_str,
            "proxy": acct.get("proxy"),
            "account_name": acct.get("name", ""),
        }

    def mark_rate_limited(self, cooldown_minutes: int = 30):
        """标记当前账号被限流。"""
        if self._current_account:
            name = self._current_account.get("name", "")
            if name:
                self._acct_mgr.mark_rate_limited(self.platform, name, cooldown_minutes)
                logger.warning(f"[SessionRouter] {self.platform}:{name} 已标记限流（{cooldown_minutes}分钟冷却）")
                self._current_account = None

    def _read_cookies(self, acct: dict) -> str:
        """从账号绑定的 cookie 文件读取 cookie 字符串。"""
        cookies_file = acct.get("cookies_file", "")
        if not cookies_file:
            return ""
        path = Path(cookies_file)
        if not path.is_absolute():
            path = _COOKIE_DIR / cookies_file
        if not path.exists():
            return ""
        try:
            data = json.loads(path.read_text("utf-8"))
            return data.get("cookies_str", "") or data.get("cookie", "")
        except (json.JSONDecodeError, OSError):
            return ""
