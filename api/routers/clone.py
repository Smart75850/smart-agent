"""VideoCloneAgent API 端点 — 视频克隆分析。"""

import ipaddress
from urllib.parse import urlparse

from fastapi import APIRouter
from pydantic import BaseModel, field_validator

router = APIRouter()

# 简单的内存任务存储
_tasks: dict[str, dict] = {}

# 允许的克隆目标域名（平台官网 + 官方短链，支持子域名）
_ALLOWED_CLONE_HOSTS = (
    "douyin.com", "iesdouyin.com", "bilibili.com", "b23.tv", "bili2233.cn",
    "xiaohongshu.com", "xhslink.com", "zhihu.com", "zhimg.com",
    "weibo.com", "weibo.cn", "kuaishou.com", "gifshow.com", "tieba.baidu.com",
)


def _is_allowed_clone_url(url: str) -> bool:
    """校验视频 URL：仅 http(s) + 平台白名单域名，拒绝 IP 字面量（防 SSRF）。"""
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host or host == "localhost":
        return False
    # 拒绝一切 IP 字面量（含内网/环回，防内网探测）
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return any(host == d or host.endswith("." + d) for d in _ALLOWED_CLONE_HOSTS)


class CloneRequest(BaseModel):
    video_url: str
    platform: str = ""          # auto-detect if empty
    max_frames: int = 30         # max keyframes to extract

    @field_validator("video_url")
    @classmethod
    def _validate_video_url(cls, v: str):
        if not _is_allowed_clone_url(v):
            raise ValueError(
                "video_url 仅支持主流平台链接（douyin/bilibili/xiaohongshu/zhihu/weibo/kuaishou/tieba），"
                "且必须为 http(s) 域名，禁止 IP 直连"
            )
        return v


class CloneTaskStatus(BaseModel):
    task_id: str
    status: str                 # "pending" | "running" | "done" | "failed"
    result: dict | None = None
    error: str = ""


@router.post("/api/clone")
async def start_clone(req: CloneRequest):
    """启动视频克隆分析任务，返回 task_id。"""
    import uuid, asyncio

    task_id = uuid.uuid4().hex[:12]
    _tasks[task_id] = {"status": "pending", "result": None, "error": ""}

    async def _run():
        from src.orchestrator.agents.video_cloner import VideoCloneAgent
        from dataclasses import asdict
        agent = VideoCloneAgent()
        try:
            _tasks[task_id]["status"] = "running"
            report = await agent.run(
                video_url=req.video_url,
                platform=req.platform,
                max_frames=req.max_frames,
            )
            _tasks[task_id] = {
                "status": "done",
                "result": asdict(report),
                "error": "",
            }
        except Exception as exc:
            _tasks[task_id] = {
                "status": "failed",
                "result": None,
                "error": str(exc),
            }

    asyncio.create_task(_run())
    return {"task_id": task_id, "status": "pending"}


@router.get("/api/clone/{task_id}")
async def get_clone_task(task_id: str) -> CloneTaskStatus:
    """获取视频克隆任务状态与结果。"""
    task = _tasks.get(task_id)
    if not task:
        return CloneTaskStatus(task_id=task_id, status="not_found", error="task_id 不存在")
    return CloneTaskStatus(
        task_id=task_id,
        status=task.get("status", "unknown"),
        result=task.get("result"),
        error=task.get("error", ""),
    )
