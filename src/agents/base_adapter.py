"""src/agents/base_adapter.py — 平台 Adapter 公共基类。

各平台 adapter 的类方法包装层高度同构（json.loads + limit 切片），
统一收敛到 JsonAdapterMixin，减少 7×5 处重复代码。

迁移方式（以 tieba_adapter.py 为范例）：
    class TiebaAdapter(JsonAdapterMixin, PlatformAdapter):
        async def search(self, keyword, limit=None, ...):
            return self._unwrap(await tieba_search(keyword), limit)
"""
import json
from typing import Optional


class JsonAdapterMixin:
    """把底层 HTTP/浏览器层返回的 JSON 字符串包装成统一格式。"""

    @staticmethod
    def _unwrap(result: str, limit: Optional[int] = None) -> list[dict]:
        """JSON 字符串 → list[dict]，可选 limit 切片。"""
        data = json.loads(result)
        return data[:limit] if limit else data

    @staticmethod
    def _unwrap_dict(result: str) -> dict:
        """JSON 字符串 → dict（用于 detail 等单对象返回）。"""
        return json.loads(result)
