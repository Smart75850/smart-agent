"""SignSrv HTTP 服务 — FastAPI on :18501。

提供签名生成和 JS 收割 API。
"""

from fastapi import FastAPI

from sign_srv.engine import SignatureEngine
from sign_srv.harvest import JSHarvester
from sign_srv.cache import CacheManager
from config.settings import settings

cache = CacheManager()
engine = SignatureEngine(cache=cache)
harvester = JSHarvester(cache=cache)


def create_app() -> FastAPI:
    app = FastAPI(title="SignSrv", version="0.1.0")

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "supported_platforms": engine.supported_platforms(),
        }

    # ── Sign endpoints ──────────────────────────────────────

    @app.post("/sign/bilibili")
    async def sign_bilibili(req: dict):
        result = await engine.generate(
            "bilibili",
            url=req.get("url", ""),
            params=req.get("params", {}),
        )
        return {
            "w_rid": result.params.get("w_rid", ""),
            "wts": result.params.get("wts", ""),
        }

    # ── Harvest endpoints ───────────────────────────────────

    @app.post("/harvest/{platform}")
    async def harvest_platform(platform: str):
        if not settings.HARVEST_ENABLED:
            return {"status": "disabled"}
        result = await harvester.harvest(platform)
        return {
            "status": "ok" if result else "empty",
            "files": result or {},
        }

    @app.post("/harvest/all")
    async def harvest_all():
        if not settings.HARVEST_ENABLED:
            return {"status": "disabled"}
        results = await harvester.harvest_all()
        return {"status": "ok", "platforms": {k: bool(v) for k, v in results.items()}}

    @app.get("/cache/stats")
    async def cache_stats():
        stats = {}
        for p in engine.supported_platforms():
            stats[p] = {
                "has_valid_js": engine.is_available(p),
                "expired": cache.is_expired(p),
            }
        return stats

    return app


# 直接启动时用
app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=18501, log_level="info")
