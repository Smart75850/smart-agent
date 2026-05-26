from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class VideoItem:
    platform: str
    title: str
    author: str
    url: str
    play_count: Optional[str] = None
    likes: Optional[str] = None
    comments: Optional[str] = None
    shares: Optional[str] = None
    danmaku: Optional[str] = None
    duration: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None
    cover_url: Optional[str] = None
    video_url: Optional[str] = None
    raw_data: dict = field(default_factory=dict)


@dataclass
class NoteItem:
    platform: str = "xiaohongshu"
    title: str = ""
    author: str = ""
    url: str = ""
    likes: Optional[str] = None
    collects: Optional[str] = None
    comments: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    has_video: bool = False
    raw_data: dict = field(default_factory=dict)
