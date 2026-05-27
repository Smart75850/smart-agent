"""B站 Wbi 签名器 — 纯 Python hashlib 实现，不需要 JS 引擎。

参考: https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/misc/sign/wbi.md
"""

import hashlib
import re
import time

import httpx
from sign_srv.platforms.base import PlatformSigner, SignResult

_MIXIN_KEY_ENC_TABLE = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3,
    45, 35, 27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39,
    12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61, 26, 17,
    0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63,
    57, 62, 11, 36, 20, 52, 44, 34,
]


class BilibiliSigner(PlatformSigner):
    platform = "bilibili"
    engine = "python"

    def __init__(self, cache=None):
        super().__init__(cache)
        self._img_key: str = ""
        self._sub_key: str = ""
        self._key_ts: float = 0

    @property
    def is_available(self) -> bool:
        return True

    async def _get_wbi_keys(self) -> tuple[str, str]:
        if self._img_key and self._sub_key and time.time() - self._key_ts < 3600:
            return self._img_key, self._sub_key

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.bilibili.com/x/web-interface/nav",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
            )
            data = resp.json().get("data", {})
            wbi_img = data.get("wbi_img", {})
            img_url = wbi_img.get("img_url", "")
            sub_url = wbi_img.get("sub_url", "")

            self._img_key = _extract_key(img_url)
            self._sub_key = _extract_key(sub_url)
            self._key_ts = time.time()
            return self._img_key, self._sub_key

    def _get_mixin_key(self, raw_key: str) -> str:
        return "".join(raw_key[i] for i in _MIXIN_KEY_ENC_TABLE[:32])

    async def sign(self, url: str = "", **kwargs) -> SignResult:
        params = dict(kwargs.get("params", {}))
        img_key, sub_key = await self._get_wbi_keys()
        mixin_key = self._get_mixin_key(img_key + sub_key)
        params["wts"] = int(time.time())
        sorted_params = sorted(params.items())
        query = "&".join(f"{k}={v}" for k, v in sorted_params)
        w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
        return SignResult(
            platform="bilibili",
            params={"w_rid": w_rid, "wts": str(params["wts"])},
        )

    def validate_js(self, js_code: str = "") -> bool:
        return True


def _extract_key(url: str) -> str:
    """从 wbi_img URL 提取密钥文件名（不含扩展名）。"""
    if not url:
        return ""
    # URL 格式: https://i0.hdslb.com/bfs/wbi/7002f6cb...png
    match = re.search(r"wbi/([^./]+)", url)
    return match.group(1) if match else ""
