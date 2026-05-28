from fastapi import APIRouter
from dataclasses import fields

from config.settings import settings

router = APIRouter()

_PLATFORMS = [
    {"id": "bilibili", "name": "B站", "hot_type": "rank", "hot_label": "排行榜", "need_login": False, "types": ["search", "rank", "detail", "comment", "user"]},
    {"id": "xiaohongshu", "name": "小紅書", "hot_type": "feed", "hot_label": "推薦熱門", "need_login": True, "types": ["search", "hot", "detail", "comment", "user"]},
    {"id": "douyin", "name": "抖音", "hot_type": "keyword", "hot_label": "熱搜關鍵詞", "need_login": True, "types": ["search", "hot", "detail", "comment", "user"]},
    {"id": "zhihu", "name": "知乎", "hot_type": "question", "hot_label": "熱榜問題", "need_login": True, "types": ["search", "hot", "detail", "comment", "user"]},
    {"id": "kuaishou", "name": "快手", "hot_type": "video", "hot_label": "熱播視頻", "need_login": False, "types": ["search", "hot", "detail", "comment", "user"]},
    {"id": "weibo", "name": "微博", "hot_type": "topic", "hot_label": "熱搜話題", "need_login": True, "types": ["search", "hot", "detail", "comment", "user"]},
    {"id": "tieba", "name": "貼吧", "hot_type": "post", "hot_label": "熱門帖子", "need_login": False, "types": ["search", "hot", "detail", "comment", "user"]},
]


@router.get("/api/platforms")
async def list_platforms():
    return {"platforms": _PLATFORMS}


@router.get("/api/config")
async def get_config():
    return {f.name: getattr(settings, f.name) for f in fields(settings)}
