"""多账号 IP 代理池管理 — 账号轮换 + 限流冷却 + proxy 绑定/回退。"""

import json
import os
import threading
import time
from pathlib import Path
from typing import Optional

from proxy.proxy_manager import ProxyManager

_ACCOUNTS_FILE = Path(__file__).resolve().parent.parent.parent / "config" / "accounts.json"

_instance = None
_lock = threading.Lock()


def get_account_manager(accounts_file: str = None) -> "AccountManager":
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = AccountManager(accounts_file)
    return _instance


class AccountManager:
    """多平台多账号轮换管理器。

    - 加载 config/accounts.json
    - get_next(platform) 轮换返回下一个可用账号
    - mark_rate_limited(platform, name) 标记限流冷却
    - 账号有绑定 proxy 时用绑定的，无绑定 fallback 到 ProxyManager 公共池
    """

    def __init__(self, accounts_file: str = None):
        self._accounts_file = accounts_file or str(_ACCOUNTS_FILE)
        self._accounts: dict[str, list[dict]] = {}
        self._index: dict[str, int] = {}
        self._cooldowns: dict[str, dict[str, float]] = {}
        self._proxy_mgr = ProxyManager()
        self._data_lock = threading.Lock()
        self._load()

    # ── 加载 ────────────────────────────────────────────

    def _load(self):
        if not os.path.exists(self._accounts_file):
            self._accounts = {}
            return
        # ensure browser_data dir exists
        accounts_path = Path(self._accounts_file)
        browser_data_dir = accounts_path.parent.parent / "browser_data"
        browser_data_dir.mkdir(exist_ok=True)

        with open(self._accounts_file, "r", encoding="utf-8") as f:
            self._accounts = json.load(f)
        for platform in self._accounts:
            if platform not in self._index:
                self._index[platform] = 0

    def reload(self):
        with self._data_lock:
            self._load()

    # ── 核心接口 ────────────────────────────────────────

    def get_next(self, platform: str) -> Optional[dict]:
        """轮换返回下一个可用账号（跳过冷却中的账号）。

        返回 dict: {name, cookies_file, proxy} 或 None。
        """
        with self._data_lock:
            accounts = self._accounts.get(platform, [])
            if not accounts:
                return None

            now = time.time()
            cooldown_map = self._cooldowns.get(platform, {})
            available = [
                (i, acc) for i, acc in enumerate(accounts)
                if now >= cooldown_map.get(acc.get("name", ""), 0)
            ]
            if not available:
                return None

            idx = self._index.get(platform, 0) % len(available)
            self._index[platform] = idx + 1
            _, acc = available[idx]

        result = dict(acc)
        if not result.get("proxy"):
            pm_proxy = self._proxy_mgr.get_next_proxy()
            if pm_proxy:
                result["proxy"] = pm_proxy
        return result

    def mark_rate_limited(self, platform: str, account_name: str,
                          cooldown_minutes: int = 30):
        """标记账号被限流，冷却期内不会被 get_next 返回。"""
        with self._data_lock:
            if platform not in self._cooldowns:
                self._cooldowns[platform] = {}
            self._cooldowns[platform][account_name] = time.time() + cooldown_minutes * 60

    def get_available(self, platform: str) -> list[dict]:
        """返回当前可用（未冷却）的账号列表。"""
        with self._data_lock:
            accounts = self._accounts.get(platform, [])
            now = time.time()
            cooldown_map = self._cooldowns.get(platform, {})
            return [
                acc for acc in accounts
                if now >= cooldown_map.get(acc.get("name", ""), 0)
            ]
