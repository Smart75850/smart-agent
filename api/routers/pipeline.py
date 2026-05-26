import asyncio
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from src.utils.browser_service import browser
from src.utils.logger import logger

router = APIRouter()

_tasks: dict[str, dict] = {}

_DEFAULT_PLATFORMS = ["bilibili", "xiaohongshu", "douyin", "zhihu", "kuaishou", "weibo", "tieba"]


class PipelineRequest(BaseModel):
    keyword: str
    platforms: list[str] = []
    limit: int = 30
    pipeline_mode: str = "full"  # simple / full


@router.post("/api/pipeline")
async def start_pipeline(req: PipelineRequest):
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"status": "running", "result": None, "error": None}
    asyncio.create_task(_run_pipeline_task(task_id, req))
    return {"task_id": task_id}


@router.get("/api/pipeline/{task_id}")
async def get_pipeline_task(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        return {"error": "task not found"}
    return {
        "task_id": task_id,
        "status": task["status"],
        "error": task.get("error"),
        "result": task.get("result"),
    }


async def _run_pipeline_task(task_id: str, req: PipelineRequest):
    from src.orchestrator import run_pipeline

    try:
        if not browser.is_running:
            await browser.start()

        platforms = req.platforms if req.platforms else _DEFAULT_PLATFORMS

        result = await run_pipeline(
            keyword=req.keyword,
            limit=req.limit,
            platforms=platforms,
            pipeline_mode=req.pipeline_mode,
        )

        _tasks[task_id].update({
            "status": "done",
            "result": {
                "keyword": req.keyword,
                "platforms": platforms,
                "pipeline_mode": req.pipeline_mode,
                "search_count": len(result.get("final_output", [])),
                "trend_summary": _first_summary(result, "trend_reports"),
                "product_summary": result.get("product_report", {}).get("summary", ""),
                "video_summary": result.get("video_report", {}).get("summary", ""),
                "sentiment_summary": result.get("sentiment_report", {}).get("summary", ""),
                "copy_summary": result.get("copy_report", {}).get("summary", ""),
                "remix_summary": result.get("remix_report", {}).get("summary", ""),
                "visual_summary": result.get("visual_report", {}).get("summary", ""),
                "full_result": result,
            },
        })
        logger.info(f"[API] pipeline {task_id}: done, {len(result.get('final_output', []))} items")
    except Exception as exc:
        err_msg = f"{type(exc).__name__}: {exc}"
        logger.error(f"[API] pipeline {task_id}: ERROR — {err_msg}")
        _tasks[task_id].update({"status": "error", "error": err_msg})


def _first_summary(result: dict, key: str) -> str:
    reports = result.get(key, {})
    if isinstance(reports, dict):
        for r in reports.values():
            if isinstance(r, dict) and r.get("summary"):
                return r["summary"]
    return ""
