"""Smart Agent Pro - 使用额度 API 路由。"""
from fastapi import APIRouter
from pydantic import BaseModel

from src.utils.usage_tracker import check_quota, get_status, activate_pro

router = APIRouter()


class ActivateRequest(BaseModel):
    key: str


@router.get("/api/usage")
async def usage_status():
    """获取当前使用状态。"""
    quota = check_quota()
    return {
        "license": quota["license"],
        "remaining": quota["remaining"],
        "total": quota["total"],
        "message": quota["message"],
        "status": get_status()
    }


@router.post("/api/activate")
async def activate(req: ActivateRequest):
    """激活 Pro 版。"""
    if activate_pro(req.key):
        return {"success": True, "message": "Pro 版已激活！"}
    return {"success": False, "message": "激活码无效"}
