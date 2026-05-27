"""签名执行引擎 — 统一接口。

根据平台自动选择 Signer：
  - py_mini_racer: douyin, kuaishou, weibo
  - execjs:        xiaohongshu, zhihu, tieba
  - python:        bilibili (Wbi)
"""

from sign_srv.cache import CacheManager
from sign_srv.platforms.douyin import DouyinSigner
from sign_srv.platforms.bilibili import BilibiliSigner
from sign_srv.platforms.base import SignResult


# 已实现的 Signer 注册表
_SIGNERS = {
    "douyin": DouyinSigner,
    "bilibili": BilibiliSigner,
    # Phase 2/3 逐步添加
}


class SignatureEngine:
    def __init__(self, cache: CacheManager = None):
        self._cache = cache or CacheManager()
        self._instances: dict[str, object] = {}

    async def generate(self, platform: str, url: str, **kwargs) -> SignResult:
        cls = _SIGNERS.get(platform)
        if cls is None:
            return SignResult(platform=platform, raw=f"unsupported_platform: {platform}")

        if platform not in self._instances:
            self._instances[platform] = cls(cache=self._cache)

        signer = self._instances[platform]
        return await signer.sign(url, **kwargs)

    def is_available(self, platform: str) -> bool:
        cls = _SIGNERS.get(platform)
        if cls is None:
            return False
        if platform not in self._instances:
            self._instances[platform] = cls(cache=self._cache)
        return self._instances[platform].is_available

    def supported_platforms(self) -> list[str]:
        return list(_SIGNERS.keys())
