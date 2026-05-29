import asyncio
import sys
import webbrowser
from pathlib import Path

# Ensure project root is on sys.path (for direct `python -m api.main`)
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: auto-open browser + start session guardian
    async def _open():
        await asyncio.sleep(1.5)
        webbrowser.open("http://localhost:8000")
    asyncio.create_task(_open())

    # 启动会话守护（15分钟自动巡检+收割）
    start_session_guardian(interval_minutes=15)

    yield
    # Shutdown: nothing to clean up yet


app = FastAPI(title="Smart Agent API", version="0.1.0", docs_url="/docs", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 使用额度中间件（试用版限 50 次）
app.add_middleware(UsageMiddleware)

from api.routers.platforms import router as platforms_router
from api.routers.crawl import router as crawl_router
from api.routers.data import router as data_router
from api.routers.ws import router as ws_router
from api.routers.pipeline import router as pipeline_router
from api.routers.usage import router as usage_router
from api.middleware import UsageMiddleware

app.include_router(platforms_router)
app.include_router(crawl_router)
app.include_router(data_router)
app.include_router(ws_router)
app.include_router(pipeline_router)
app.include_router(usage_router)

# ── Session 守护 ─────────────────────────────────────────────
from src.utils.session_manager import get_health_status, start_session_guardian, harvest_all

@app.get("/api/sessions/status")
async def sessions_status():
    return {"sessions": get_health_status()}

_guardian_started = False

@app.post("/api/sessions/refresh")
async def sessions_refresh():
    global _guardian_started
    if not _guardian_started:
        start_session_guardian(interval_minutes=15)
        _guardian_started = True
    results = await harvest_all()
    # 收完立即更新健康状态
    for plat, ok in results.items():
        from src.utils.session_manager import _last_health
        import time
        _last_health[plat] = {"healthy": ok, "last_check": time.strftime("%H:%M:%S"), "last_ok": time.strftime("%H:%M:%S") if ok else "", "error": "" if ok else "unreachable"}
    return {"harvested": {k: v for k, v in results.items()}}

# ── Watcher API ───────────────────────────────────────────────
_watcher_instance: "KeywordWatcher | None" = None

@app.get("/api/watcher/status")
async def watcher_status():
    if _watcher_instance is None:
        return {"running": False, "message": "watcher 未启动"}
    return _watcher_instance.status()

@app.post("/api/watcher/start")
async def watcher_start(keywords: str = "", platforms: str = "bilibili", interval: int = 60):
    global _watcher_instance
    if _watcher_instance and _watcher_instance._running:
        return {"message": "watcher 已在运行", "status": _watcher_instance.status()}
    from src.utils.watcher import KeywordWatcher
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    if not kw_list:
        return {"error": "请提供 keywords 参数（逗号分隔）"}
    plat_list = [p.strip() for p in platforms.split(",") if p.strip()]
    _watcher_instance = KeywordWatcher(keywords=kw_list, platforms=plat_list, interval_minutes=interval)
    asyncio.create_task(_watcher_instance.watch_loop())
    return {"message": "watcher 已启动", "keywords": kw_list, "interval_min": interval}

@app.post("/api/watcher/stop")
async def watcher_stop():
    global _watcher_instance
    if _watcher_instance:
        _watcher_instance.stop()
        _watcher_instance = None
        return {"message": "watcher 已停止"}
    return {"message": "watcher 未在运行"}

# Serve WebUI — 用显式路由而非 mount 避免拦截 /docs
WEBUI_DIR = Path(__file__).parent / "webui"
_INDEX_HTML = (WEBUI_DIR / "index.html").read_text(encoding="utf-8") if (WEBUI_DIR / "index.html").exists() else ""

@app.get("/")
async def serve_webui():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=_INDEX_HTML)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)
