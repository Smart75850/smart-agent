from fastapi import APIRouter
from dataclasses import fields

from config.settings import settings

router = APIRouter()

_PLATFORMS = [
    {"id": "bilibili", "name": "B站", "need_login": False, "types": ["search", "rank", "detail", "comment", "user"]},
    {"id": "xiaohongshu", "name": "小紅書", "need_login": True, "types": ["search", "hot", "detail", "comment", "user"]},
    {"id": "douyin", "name": "抖音", "need_login": True, "types": ["search", "hot", "detail", "comment", "user"]},
    {"id": "zhihu", "name": "知乎", "need_login": True, "types": ["search", "hot", "detail", "comment", "user"]},
    {"id": "kuaishou", "name": "快手", "need_login": True, "types": ["search", "hot", "detail", "comment", "user"]},
]


@router.get("/api/platforms")
async def list_platforms():
    return {"platforms": _PLATFORMS}


@router.get("/api/config")
async def get_config():
    return {f.name: getattr(settings, f.name) for f in fields(settings)}
