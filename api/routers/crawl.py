import asyncio
import json
import os
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from src.utils.browser_service import browser
from src.utils.logger import logger
from src.utils.checkpoint import get_checkpoint
from store import get_store, save_with_dedup
from config.settings import settings

router = APIRouter()

_ADAPTERS = {}
_tasks: dict[str, dict] = {}


class CrawlRequest(BaseModel):
    platform: str = ""
    platforms: list[str] = []
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
    resp = {
        "task_id": task_id,
        "status": task["status"],
        "result_count": task.get("result_count", 0),
        "error": task.get("error"),
    }
    if task["status"] == "done" and task.get("result") is not None:
        resp["result"] = task["result"]
    return resp


async def _run_crawl(task_id: str, req: CrawlRequest):
    try:
        os.environ["BROWSER_ENGINE"] = req.engine
        if not browser.is_running:
            await browser.start()

        action = req.type
        keyword = req.keyword
        ck = get_checkpoint()

        # Determine target platforms
        target_platforms = req.platforms if req.platforms else ([req.platform] if req.platform else [])
        if not target_platforms:
            raise ValueError("请指定 platform 或 platforms")

        if len(target_platforms) > 1:
            # Multi-platform: concurrent execution
            _lazy_init_adapters()
            method_name = _TYPE_METHOD.get(action, "search")
            kwargs = _get_method_kwargs(method_name, keyword, req.limit)

            async def _call_one(plat):
                ck.save_task(plat, action, keyword, status="running")
                adapter = _ADAPTERS.get(plat)
                if adapter is None:
                    return plat, {"error": f"唔支援嘅平台: {plat}"}
                try:
                    method = getattr(adapter, method_name)
                    data = await method(**kwargs)
                    items = data[:req.limit] if isinstance(data, list) and req.limit else data
                    if not isinstance(items, list):
                        items = [items]
                    from src.aggregator import _normalize
                    items = [_normalize(it, plat) for it in items if isinstance(it, dict)]
                    new_items = ck.filter_new_items(items, plat)
                    count = len(new_items)
                    if new_items:
                        store = get_store(settings.STORE_BACKEND)
                        store.save(new_items, settings.OUTPUT_DIR, f"{plat}_{action}")
                    ck.mark_done(plat, action, keyword, collected_count=count)
                    logger.info(f"[API] {plat}_{action}: {count} 条 (新增)")
                    return plat, {"items": new_items, "count": count}
                except Exception as e:
                    err = f"{type(e).__name__}: {e}"
                    ck.mark_failed(plat, action, keyword, error_msg=err)
                    logger.error(f"[API] {plat}_{action}: ERROR — {err}")
                    return plat, {"error": err}

            results = dict(await asyncio.gather(*[_call_one(p) for p in target_platforms], return_exceptions=True))
            search_results = {}
            all_items = []
            for plat, r in results.items():
                if isinstance(r, dict):
                    if "items" in r:
                        search_results[plat] = r["items"]
                        all_items.extend([{**it, "platform": plat} for it in r["items"]])
                    elif "error" in r:
                        search_results[plat] = r

            def _hot_score(item):
                try: return int(item.get("plays", 0) or 0) + int(item.get("likes", 0) or 0) * 2
                except: return 0
            all_items.sort(key=_hot_score, reverse=True)

            errors = {plat: r.get("error", "") for plat, r in results.items() if isinstance(r, dict) and "error" in r}
            total = sum(r.get("count", 0) for r in results.values() if isinstance(r, dict))
            _tasks[task_id].update({
                "status": "done",
                "result": {"search_results": search_results, "items": all_items, "errors": errors},
                "result_count": total,
            })
        else:
            # Single platform: original logic
            platform = target_platforms[0]
            ck.save_task(platform, action, keyword, status="running")

            if action == "user" and platform == "douyin" and keyword:
                from src.agents.douyin_adapter import douyin_user_videos
                raw = await douyin_user_videos(user_id=keyword)
                data = json.loads(raw)
            else:
                _lazy_init_adapters()
                adapter = _ADAPTERS.get(platform)
                if adapter is None:
                    raise ValueError(f"唔支援嘅平台: {platform}")
                method_name = _TYPE_METHOD.get(action)
                if method_name is None:
                    raise ValueError(f"唔支援嘅操作: {action}")

                kwargs = _get_method_kwargs(method_name, keyword, req.limit)
                method = getattr(adapter, method_name)
                data = await method(**kwargs)

            if isinstance(data, list) and req.limit:
                data = data[:req.limit]

            # 归一化字段名（统一各平台差异）
            if isinstance(data, list) and action in ("search", "hot"):
                from src.aggregator import _normalize
                data = [_normalize(it, platform) for it in data if isinstance(it, dict)]

            # Tag each item with platform for frontend display
            if isinstance(data, list):
                for it in data:
                    if isinstance(it, dict) and "platform" not in it:
                        it["platform"] = platform
                try:
                    data.sort(key=lambda it: (int(it.get("plays", 0) or 0) + int(it.get("likes", 0) or 0) * 2), reverse=True)
                except Exception:
                    pass

            key = f"{platform}_{action}"
            store = get_store(settings.STORE_BACKEND)
            if isinstance(data, list):
                if action in ("comment",):
                    new_data = data  # 评论不参与去重
                else:
                    new_data = ck.filter_new_items(data, platform)
                filepath = store.save(new_data, settings.OUTPUT_DIR, key) if new_data else ""
                count = len(new_data)
                data = new_data
            else:
                filepath = store.save(data, settings.OUTPUT_DIR, key)
                count = 1
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
        if req.platform:
            get_checkpoint().mark_failed(req.platform, req.type, req.keyword or "", error_msg=err_msg)


def _get_method_kwargs(method_name, keyword, limit=20):
    if method_name == "search":
        kw = {}
        if keyword: kw["keyword"] = keyword
        kw["limit"] = limit
        return kw
    elif method_name in ("detail", "comment"):
        return {"item_id": keyword, "limit": limit}
    elif method_name == "user":
        return {"user_id": keyword}
    return {}
