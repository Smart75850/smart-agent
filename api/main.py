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
    # Startup: auto-open browser
    async def _open():
        await asyncio.sleep(1.5)
        webbrowser.open("http://localhost:8000")
    asyncio.create_task(_open())
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

from api.routers.platforms import router as platforms_router
from api.routers.crawl import router as crawl_router
from api.routers.data import router as data_router
from api.routers.ws import router as ws_router

app.include_router(platforms_router)
app.include_router(crawl_router)
app.include_router(data_router)
app.include_router(ws_router)

# Serve WebUI static files (after API routers to avoid route conflict)
WEBUI_DIR = Path(__file__).parent / "webui"
if WEBUI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEBUI_DIR), html=True), name="webui")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)
