"""抖音 a_bogus / x_bogus 签名器。

基于 py_mini_racer (V8) 执行混淆 JS，无需浏览器。
使用 Camoufox 收割的 a_bogus.js 作为签名源。
"""

import json
from urllib.parse import urlparse

from sign_srv.platforms.base import PlatformSigner, SignResult
from sign_srv.runtimes.py_mini_racer import V8Runtime


class DouyinSigner(PlatformSigner):
    platform = "douyin"
    engine = "py_mini_racer"

    async def sign(self, url: str, user_agent: str = "", **kwargs) -> SignResult:
        js_key = "a_bogus"
        js_code = self._cache.load_js(self.platform, js_key)
        if not js_code:
            return SignResult(platform="douyin", raw="no_js_cache")

        runtime = V8Runtime(js_code)
        parsed = urlparse(url)
        query = parsed.query
        ua = user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

        try:
            ab = runtime.call("generate_a_bogus", query, ua)
            xb = ""
            try:
                xb = runtime.call("sign", query, ua)
            except Exception:
                pass

            return SignResult(
                platform="douyin",
                params={"a_bogus": ab.strip() if ab else "", "x_bogus": xb.strip() if xb else ""},
                raw=json.dumps({"a_bogus": ab, "x_bogus": xb}, ensure_ascii=False),
            )
        except Exception as exc:
            return SignResult(platform="douyin", raw=f"engine_error: {exc}")

    def validate_js(self, js_code: str) -> bool:
        try:
            runtime = V8Runtime(js_code)
            result = runtime.call("generate_a_bogus", "test=1", "Mozilla/5.0")
            return bool(result and len(result) > 10)
        except Exception:
            return False
