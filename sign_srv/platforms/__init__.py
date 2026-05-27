"""平台簽名器 — 每個平台一個 Signer。"""

from sign_srv.platforms.base import PlatformSigner, SignResult
from sign_srv.platforms.douyin import DouyinSigner
from sign_srv.platforms.bilibili import BilibiliSigner

__all__ = ["PlatformSigner", "SignResult", "DouyinSigner", "BilibiliSigner"]
