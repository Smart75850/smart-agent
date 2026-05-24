import time
import asyncio
from typing import Any, Optional


class MemoryCache:
    """In-memory cache with TTL support + asyncio.Lock thread-safety."""

    def __init__(self, ttl: int = 300):
        self._ttl = ttl
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            expires, value = entry
            if time.time() > expires:
                del self._data[key]
                return None
            return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        async with self._lock:
            self._data[key] = (time.time() + (ttl or self._ttl), value)

    async def clear(self):
        async with self._lock:
            self._data.clear()

    @property
    def size(self) -> int:
        return len(self._data)
