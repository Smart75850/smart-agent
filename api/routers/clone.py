"""VideoCloneAgent API 端点 — 视频克隆分析。"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

# 简单的内存任务存储
_tasks: dict[str, dict] = {}


class CloneRequest(BaseModel):
    video_url: str
    platform: str = ""          # auto-detect if empty
    max_frames: int = 30         # max keyframes to extract


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
