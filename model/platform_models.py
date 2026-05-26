"""平台数据模型 — 匹配适配器实际输出字段。

注：当前 pipeline 使用 dict 流通，此 dataclass 用于文档和未来类型化重构。
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VideoItem:
    platform: str = ""
    title: str = ""
    author: str = ""
    plays: str = ""
    likes: str = ""
    link: str = ""
    platform_id: str = ""           # aweme_id / photo_id / bvid / aid
    cover_url: Optional[str] = None
    video_url: Optional[str] = None
    duration: Optional[str] = None
    description: Optional[str] = None
    date: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class NoteItem:
    platform: str = "xiaohongshu"
    title: str = ""
    author: str = ""
    likes: str = ""
    link: str = ""
    platform_id: str = ""
    cover_url: Optional[str] = None
    collects: Optional[str] = None
    comments: Optional[str] = None
    description: Optional[str] = None
    date: Optional[str] = None
    has_video: bool = False
    raw: dict = field(default_factory=dict)
