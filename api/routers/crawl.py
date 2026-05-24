import asyncio
import json
import os
import uuid

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from src.utils.browser_service import browser
from src.utils.logger import logger
from store import get_store
from config.settings import settings

router = APIRouter()

_ADAPTERS = {}
_tasks: dict[str, dict] = {}


class CrawlRequest(BaseModel):
    platform: str
    type: str = "search"
    keyword: str = ""
    limit: int = 20
    engine: str = "playwright"


def _lazy_init_adapters():
    if _ADAPTERS:
        return
    from src.agents.bilibili_adapter import BilibiliAdapter
    from src.agents.xiaohongshu_adapter import XiaohongshuAdapter
    from src.agents.douyin_adapter import DouyinAdapter
    from src.agents.zhihu_adapter import ZhihuAdapter
    from src.agents.kuaishou_adapter import KuaishouAdapter
    _ADAPTERS.update({
        "bilibili": BilibiliAdapter(),
        "xiaohongshu": XiaohongshuAdapter(),
        "douyin": DouyinAdapter(),
        "zhihu": ZhihuAdapter(),
        "kuaishou": KuaishouAdapter(),
    })


_TYPE_METHOD = {
    "search": "search",
    "hot": "hot",
    "rank": "hot",
    "detail": "detail",
    "comment": "comment",
    "user": "user",
}


@router.post("/api/crawl")
async def start_crawl(req: CrawlRequest):
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"status": "running", "result": None, "error": None, "result_count": 0}
    asyncio.create_task(_run_crawl(task_id, req))
    return {"task_id": task_id}


@router.get("/api/crawl/{task_id}")
async def get_task(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        return {"error": "task not found"}
    return {
        "task_id": task_id,
        "status": task["status"],
        "result_count": task.get("result_count", 0),
        "error": task.get("error"),
    }


async def _run_crawl(task_id: str, req: CrawlRequest):
    try:
        os.environ["BROWSER_ENGINE"] = req.engine
        if not browser.is_running:
            await browser.start()

        platform = req.platform
        action = req.type

        if action == "user" and platform == "douyin":
            # 兼容舊 raw function
            from src.agents.douyin_adapter import douyin_user_videos
            raw = await douyin_user_videos(user_id=req.keyword)
            data = json.loads(raw)
        else:
            _lazy_init_adapters()
            adapter = _ADAPTERS.get(platform)
            if adapter is None:
                raise ValueError(f"唔支援嘅平台: {platform}")
            method_name = _TYPE_METHOD.get(action)
            if method_name is None:
                raise ValueError(f"唔支援嘅操作: {action}")

            if method_name == "search":
                kwargs = {"keyword": req.keyword} if req.keyword else {}
            elif method_name in ("detail", "comment"):
                kwargs = {"item_id": req.keyword}
            elif method_name == "user":
                kwargs = {"user_id": req.keyword}
            else:
                kwargs = {}

            method = getattr(adapter, method_name)
            data = await method(**kwargs)

        if isinstance(data, list) and req.limit:
            data = data[:req.limit]

        key = f"{platform}_{action}"
        store = get_store(settings.STORE_BACKEND)
        filepath = store.save(data, settings.OUTPUT_DIR, key)

        count = len(data) if isinstance(data, list) else 1
        _tasks[task_id].update({
            "status": "done",
            "result": data,
            "result_count": count,
            "filepath": filepath,
        })
        logger.info(f"[API] {key}: {count} 條 → {filepath}")
    except Exception as exc:
        err_msg = f"{type(exc).__name__}: {exc}"
        logger.error(f"[API] crawl {task_id}: ERROR — {err_msg}")
        _tasks[task_id].update({"status": "error", "error": err_msg})
