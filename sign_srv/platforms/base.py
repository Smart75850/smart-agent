"""平台签名器抽象基类。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from sign_srv.cache import CacheManager


@dataclass
class SignResult:
    platform: str
    params: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    cookies: dict[str, str] = field(default_factory=dict)
    raw: str = ""


class PlatformSigner(ABC):
    def __init__(self, cache: CacheManager = None):
        self._cache = cache or CacheManager()

    @property
    @abstractmethod
    def platform(self) -> str: ...

    @property
    def engine(self) -> str:
        return "py_mini_racer"

    @property
    def is_available(self) -> bool:
        return self._cache.has_valid_js(self.platform)

    @abstractmethod
    async def sign(self, url: str, **kwargs) -> SignResult: ...

    def validate_js(self, js_code: str) -> bool:
        return True
