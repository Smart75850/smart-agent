"""Smart Agent Pro — Python Sidecar 服务。

Go 主进程通过 HTTP 调用本服务进行浏览器爬取和 Agent 分析。
端口 18500（不与 WebUI 8000 冲突）。

启动: python sidecar_server.py
"""

import os
import sys
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

# 确保项目根目录在 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import settings
from src.utils.logger import logger
from src.utils.browser_service import browser
from src.orchestrator.nodes import _get_adapter, _retry
from src.aggregator import _normalize

# ── Agent imports ──────────────────────────────────────────
from src.orchestrator.agents.trend_scout import TrendScout
from src.orchestrator.agents.product_miner import ProductMiner
from src.orchestrator.agents.video_analyst import VideoAnalyst
from src.orchestrator.agents.sentiment_reader import SentimentReader
from src.orchestrator.agents.copy_writer import CopyWriter
from src.orchestrator.agents.content_remixer import ContentRemixer, RemixInput
from src.orchestrator.agents.pic_tactic import PicTactic

_AGENTS = {
    "trend":        TrendScout(),
    "product":      ProductMiner(),
    "video":        VideoAnalyst(),
    "sentiment":    SentimentReader(),
    "copy":         CopyWriter(),
    "remix":        ContentRemixer(),
    "pic":          PicTactic(),
}


# ── Lifespan ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[sidecar] 启动浏览器服务...")
    await browser.start()

    # SignSrv: 挂载签名服务子应用
    if settings.SIGN_SRV_ENABLED:
        try:
            from sign_srv.server import create_app as create_sign_app, cache as sign_cache
            sign_app = create_sign_app()
            app.mount("/sign", sign_app)
            logger.info("[sidecar] SignSrv 已挂载: /sign")

            # 抖音 JS 种子已移至私有仓库 smart-agent-re，此处跳过
        except Exception as exc:
            logger.warning(f"[sidecar] SignSrv 加载失败: {exc}")

    logger.info("[sidecar] Sidecar 就绪: http://localhost:18500")
    yield
    logger.info("[sidecar] 关闭浏览器服务...")
    await browser.close()


app = FastAPI(title="Smart Agent Sidecar", version="0.1.0", lifespan=lifespan)


# ── Request Models ──────────────────────────────────────────
class CrawlRequest(BaseModel):
    platform: str
    keyword: str = ""
    limit: int = 20


class AgentRequest(BaseModel):
    agent: str
    state: dict = {}


# ── Health ──────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "agents": list(_AGENTS.keys())}


# ── Crawl Endpoints ─────────────────────────────────────────
@app.post("/crawl/search")
async def crawl_search(req: CrawlRequest):
    adapter = _get_adapter(req.platform)
    if adapter is None:
        return {"items": [], "error": f"unknown platform: {req.platform}"}
    try:
        raw = await _retry(lambda: adapter.search(req.keyword, limit=req.limit))
        items = [_normalize(it, req.platform) for it in (raw if isinstance(raw, list) else [])]
        logger.info(f"[sidecar] {req.platform} search: {len(items)} 条")
        return {"items": items, "error": ""}
    except Exception as exc:
        logger.warning(f"[sidecar] {req.platform} search failed: {exc}")
        return {"items": [], "error": str(exc)}


@app.post("/crawl/hot")
async def crawl_hot(req: CrawlRequest):
    adapter = _get_adapter(req.platform)
    if adapter is None:
        return {"items": [], "error": f"unknown platform: {req.platform}"}
    try:
        raw = await _retry(lambda: adapter.hot(limit=req.limit))
        items = [_normalize(it, req.platform) for it in (raw if isinstance(raw, list) else [])]
        logger.info(f"[sidecar] {req.platform} hot: {len(items)} 条")
        return {"items": items, "error": ""}
    except Exception as exc:
        logger.warning(f"[sidecar] {req.platform} hot failed: {exc}")
        return {"items": [], "error": str(exc)}


# ── Agent Endpoints ─────────────────────────────────────────
@app.post("/agent/trend")
async def agent_trend(req: AgentRequest):
    """TrendScout — 爆款趋势分析。"""
    state = req.state
    scout = _AGENTS["trend"]
    report = await scout.run(
        platform=state.get("platform", "bilibili"),
        keyword=state.get("keyword", ""),
        limit=state.get("limit", 20),
    )
    from dataclasses import asdict
    return asdict(report)


@app.post("/agent/product")
async def agent_product(req: AgentRequest):
    """ProductMiner — 选品分析。"""
    state = req.state
    items = state.get("merged_items", []) or state.get("scored_items", [])
    report = await _AGENTS["product"].run(items=items, keyword=state.get("keyword", ""))
    from dataclasses import asdict
    return asdict(report)


@app.post("/agent/video")
async def agent_video(req: AgentRequest):
    """VideoAnalyst — 视频结构拆解。"""
    state = req.state
    items = state.get("merged_items", []) or state.get("scored_items", [])
    platform = state.get("platforms", ["bilibili"])
    if isinstance(platform, list):
        platform = platform[0] if platform else "bilibili"
    report = await _AGENTS["video"].run(items=items, platform=platform)
    from dataclasses import asdict
    return asdict(report)


@app.post("/agent/sentiment")
async def agent_sentiment(req: AgentRequest):
    """SentimentReader — 评论情绪分析。"""
    state = req.state
    items = state.get("merged_items", []) or state.get("scored_items", [])
    platform = state.get("platforms", ["bilibili"])
    if isinstance(platform, list):
        platform = platform[0] if platform else "bilibili"
    report = await _AGENTS["sentiment"].run(items=items, platform=platform, fetch_comments=False)
    from dataclasses import asdict
    return asdict(report)


@app.post("/agent/copy")
async def agent_copy(req: AgentRequest):
    """CopyWriter — 营销文案生成。"""
    state = req.state
    from dataclasses import asdict
    report = await _AGENTS["copy"].run(
        keyword=state.get("keyword", ""),
        trend_items=_extract_items(state.get("trend_reports", {})),
        products=_extract_items(state.get("product_report", {})),
        video_breakdowns=_extract_items(state.get("video_report", {})),
    )
    return asdict(report)


@app.post("/agent/remix")
async def agent_remix(req: AgentRequest):
    """ContentRemixer — 数据分析/总结/改写。"""
    state = req.state
    inp = RemixInput(
        mode=state.get("remix_mode", "summarize"),
        topic=state.get("keyword", ""),
        raw_items=state.get("merged_items", []) or state.get("scored_items", []),
        trend_reports=state.get("trend_reports", {}),
        product_report=state.get("product_report", {}),
        video_report=state.get("video_report", {}),
        sentiment_report=state.get("sentiment_report", {}),
    )
    report = await _AGENTS["remix"].run(inp)
    from dataclasses import asdict
    return asdict(report)


@app.post("/agent/pic")
async def agent_pic(req: AgentRequest):
    """PicTactic — 智能配图策略。"""
    state = req.state
    from dataclasses import asdict
    report = await _AGENTS["pic"].run(
        mode=state.get("pic_mode", "social"),
        topic=state.get("keyword", ""),
        platform=state.get("platform", ""),
        trend_items=_extract_items(state.get("trend_reports", {})),
        products=_extract_items(state.get("product_report", {})),
    )
    return asdict(report)


# ── Helper ──────────────────────────────────────────────────
def _extract_items(data) -> list:
    """从 agent report dict 中提取 items 列表。"""
    if not data:
        return []
    if isinstance(data, dict):
        return data.get("items", [])
    if isinstance(data, list):
        return data
    return []


def _seed_douyin_js(cache):
    """预装已验证的抖音 a_bogus JS（从 yingzi4f/a_bogus 提取）。

    仅在缓存为空时执行，避免覆盖已有 JS。
    """
    import os as _os
    try:
        if cache.has_valid_js("douyin", "a_bogus"):
            return
        js_path = _os.path.join(_os.path.dirname(__file__), "sign_srv", "js_seed", "a_bogus.js")
        if not _os.path.exists(js_path):
            # 尝试从测试目录复制
            src = r"C:\tmp\a_bogus_test\utils\a_bogus.js"
            if _os.path.exists(src):
                cache.save_js("douyin", "a_bogus", open(src, encoding="utf-8").read(), "seed")
                logger.info("[sidecar] 已预装 douyin a_bogus JS")
        else:
            cache.save_js("douyin", "a_bogus", open(js_path, encoding="utf-8").read(), "seed")
            logger.info("[sidecar] 已预装 douyin a_bogus JS")
    except Exception as exc:
        logger.warning(f"[sidecar] 预装 douyin JS 失败: {exc}")


# ── Main ────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=18500, log_level="info")
