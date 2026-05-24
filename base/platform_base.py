from abc import ABC, abstractmethod
from typing import Optional


class PlatformAdapter(ABC):
    """平台 Adapter 抽象基類。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """平台名稱，例如 bilibili / douyin"""
        ...

    @property
    @abstractmethod
    def need_login(self) -> bool:
        """係咪需要登入先用得"""
        ...

    @abstractmethod
    async def search(self, keyword: str, limit: Optional[int] = None) -> list[dict]:
        """搜索"""
        ...

    async def hot(self, limit: Optional[int] = None) -> list[dict]:
        """熱榜/排行榜（可選）"""
        raise NotImplementedError

    async def detail(self, item_id: str, xsec_token: str = "", **kwargs) -> dict:
        """詳情（可選）"""
        raise NotImplementedError

    async def comment(self, item_id: str, limit: Optional[int] = None) -> list[dict]:
        """評論（可選）"""
        raise NotImplementedError

    async def user(self, user_id: str, limit: Optional[int] = None) -> list[dict]:
        """用戶主頁內容（可選）"""
        raise NotImplementedError
