import asyncio
import json
import os
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from src.utils.browser_service import browser
from src.utils.logger import logger
from src.utils.checkpoint import get_checkpoint
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
    engine: str = "auto"


def _lazy_init_adapters():
    if _ADAPTERS:
        return
    from src.agents.bilibili_adapter import BilibiliAdapter
    from src.agents.xiaohongshu_adapter import XiaohongshuAdapter
    from src.agents.douyin_adapter import DouyinAdapter
    from src.agents.zhihu_adapter import ZhihuAdapter
    from src.agents.kuaishou_adapter import KuaishouAdapter
    from src.agents.weibo_adapter import WeiboAdapter
    from src.agents.tieba_adapter import TiebaAdapter
    _ADAPTERS.update({
        "bilibili": BilibiliAdapter(),
        "xiaohongshu": XiaohongshuAdapter(),
        "douyin": DouyinAdapter(),
        "zhihu": ZhihuAdapter(),
        "kuaishou": KuaishouAdapter(),
        "weibo": WeiboAdapter(),
        "tieba": TiebaAdapter(),
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
        keyword = req.keyword
        ck = get_checkpoint()
        ck.save_task(platform, action, keyword, status="running")

        if action == "user" and platform == "douyin" and keyword:
            # 兼容舊 raw function
            from src.agents.douyin_adapter import douyin_user_videos
            raw = await douyin_user_videos(user_id=keyword)
            data = json.loads(raw)
        elif action == "user" and platform == "douyin":
            raise ValueError("user 模式需要 keyword 作為 user_id")
        else:
            _lazy_init_adapters()
            adapter = _ADAPTERS.get(platform)
            if adapter is None:
                raise ValueError(f"唔支援嘅平台: {platform}")
            method_name = _TYPE_METHOD.get(action)
            if method_name is None:
                raise ValueError(f"唔支援嘅操作: {action}")

            if method_name == "search":
                kwargs = {"keyword": keyword} if keyword else {}
            elif method_name in ("detail", "comment"):
                kwargs = {"item_id": keyword}
            elif method_name == "user":
                kwargs = {"user_id": keyword}
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
        ck.mark_done(platform, action, keyword, collected_count=count)
        logger.info(f"[API] {key}: {count} 條 → {filepath}")
    except Exception as exc:
        err_msg = f"{type(exc).__name__}: {exc}"
        logger.error(f"[API] crawl {task_id}: ERROR — {err_msg}")
        _tasks[task_id].update({"status": "error", "error": err_msg})
        if keyword:
            ck.mark_failed(platform, action, keyword, error_msg=err_msg)
        elif req.platform and req.type:
            ck.mark_failed(req.platform, req.type, req.keyword or "", error_msg=err_msg)
