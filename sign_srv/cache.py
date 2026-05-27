"""JS 文件缓存与版本管理。

每个平台一个子目录，包含收割的 JS 文件和 manifest.json。
"""

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class JSManifest:
    platform: str
    last_harvest: str = ""
    js_files: dict[str, dict] = field(default_factory=dict)
    test_result: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "last_harvest": self.last_harvest,
            "js_files": self.js_files,
            "test_result": self.test_result,
        }


class CacheManager:
    def __init__(self, cache_dir: str = None):
        if cache_dir is None:
            cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sign_srv", "js_cache")
        self._root = Path(cache_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    # ── public ──────────────────────────────────────────────

    def has_valid_js(self, platform: str, key: str = None) -> bool:
        manifest = self._load_manifest(platform)
        if not manifest or not manifest.js_files:
            return False
        if key:
            return key in manifest.js_files
        return True

    def load_js(self, platform: str, key: str) -> Optional[str]:
        manifest = self._load_manifest(platform)
        if not manifest or key not in manifest.js_files:
            return None
        file_path = self._dir(platform) / manifest.js_files[key]["file"]
        if not file_path.exists():
            return None
        return file_path.read_text(encoding="utf-8")

    def save_js(self, platform: str, key: str, js_code: str, source_url: str = "") -> dict:
        new_hash = self._sha256(js_code)
        existing = self._load_manifest(platform)

        # 检查是否与现有内容相同（去重）
        if existing and key in existing.js_files:
            old_hash = existing.js_files[key].get("sha256", "")
            if old_hash == new_hash:
                return existing.js_files[key]

        # 保存 JS 文件
        date_str = time.strftime("%Y%m%d_%H%M%S")
        file_name = f"{key}_{date_str}.js"
        file_path = self._dir(platform) / file_name
        file_path.write_text(js_code, encoding="utf-8")

        # 更新 manifest
        manifest = existing or JSManifest(platform=platform)
        manifest.last_harvest = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        manifest.js_files[key] = {
            "file": file_name,
            "sha256": new_hash,
            "size": len(js_code),
            "source_url": source_url,
        }
        self._save_manifest(platform, manifest)

        return manifest.js_files[key]

    def get_active_version(self, platform: str, key: str) -> Optional[str]:
        manifest = self._load_manifest(platform)
        if not manifest or key not in manifest.js_files:
            return None
        return manifest.js_files[key].get("sha256", "")

    def set_test_result(self, platform: str, result: str, details: str = ""):
        manifest = self._load_manifest(platform)
        if manifest:
            manifest.test_result = {
                "result": result,
                "tested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "details": details,
            }
            self._save_manifest(platform, manifest)

    def is_expired(self, platform: str, ttl_hours: int = 24) -> bool:
        manifest = self._load_manifest(platform)
        if not manifest or not manifest.last_harvest:
            return True
        try:
            last = time.strptime(manifest.last_harvest, "%Y-%m-%dT%H:%M:%SZ")
            elapsed = time.time() - time.mktime(last)
            return elapsed > ttl_hours * 3600
        except (ValueError, OSError):
            return True

    # ── internal ───────────────────────────────────────────

    def _dir(self, platform: str) -> Path:
        p = self._root / platform
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _manifest_path(self, platform: str) -> Path:
        return self._dir(platform) / "manifest.json"

    def _load_manifest(self, platform: str) -> Optional[JSManifest]:
        path = self._manifest_path(platform)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return JSManifest(**data)
        except (json.JSONDecodeError, TypeError):
            return None

    def _save_manifest(self, platform: str, manifest: JSManifest):
        self._manifest_path(platform).write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _sha256(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:16]
