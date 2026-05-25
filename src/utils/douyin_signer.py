"""抖音 a_bogus 本地签名 — Python 原生实现，基于 TikTokDownloader 同 gmssl SM3"""
import random
import urllib.parse

from src.utils.abogus import ABogus

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


class DouyinSigner:
    """抖音 a_bogus 签名器"""

    def __init__(self, user_agent: str = DEFAULT_UA):
        self._user_agent = user_agent

    def sign(self, url: str, user_agent: str = "") -> str:
        """对 URL 生成 a_bogus 签名"""
        ua = user_agent or self._user_agent
        query = urllib.parse.urlparse(url).query
        ab = ABogus(ua)
        return ab.get_value(query, "GET")

    @staticmethod
    def generate_ms_token(length: int = 107) -> str:
        """生成随机 msToken"""
        chars = "ABCDEFGHIGKLMNOPQRSTUVWXYZabcdefghigklmnopqrstuvwxyz0123456789="
        return "".join(random.choice(chars) for _ in range(length))


_signer: DouyinSigner | None = None


def get_signer() -> DouyinSigner:
    global _signer
    if _signer is None:
        _signer = DouyinSigner()
    return _signer


def sign_url(url: str, user_agent: str = "") -> str:
    """快捷签名：传入 URL，返回带 a_bogus 的完整 URL"""
    ua = user_agent or DEFAULT_UA
    ab = get_signer().sign(url, ua)
    return f"{url}&a_bogus={ab}"
