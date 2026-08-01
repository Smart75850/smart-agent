from __future__ import annotations
"""高层 API — 一鸡两味（同步/流式）。"""
import hashlib
from typing import AsyncIterator

from src.orchestrator.state import PipelineState
from src.orchestrator.graph import compiled_graph
from src.utils.logger import logger
from config.settings import settings

_DEFAULT_PLATFORMS = ["bilibili", "xiaohongshu", "douyin", "zhihu", "kuaishou", "weibo", "tieba"]


def _build_initial_state(
    keyword: str,
    limit: int,
    platforms: list[str] | None,
    llm_filter: bool,
    pipeline_mode: str = "simple",
    analysis_mode: str = "keyword",
    sort_type: int | None = None,
    publish_time: int = 0,
    search_channel: str = "",
    include_raw: bool = False,
) -> PipelineState:
    # full 模式默认按最热排序，确保高互动内容优先（评论更多→SentimentReader 能用）
    if sort_type is None:
        sort_type = 2 if pipeline_mode == "full" else 0
    return {
        "keyword": keyword,
        "analysis_mode": analysis_mode,
        "limit": limit,
        "platforms": platforms or _DEFAULT_PLATFORMS,
        "llm_filter": llm_filter,
        "pipeline_mode": pipeline_mode,
        "sort_type": sort_type,
        "publish_time": publish_time,
        "search_channel": search_channel,
        "include_raw": include_raw,
        "search_results": {},
        "merged_items": [],
        "filtered_items": [],
        "scored_items": [],
        "errors": {},
        "final_output": [],
    }


def _make_config(keyword: str, platforms: list[str]) -> dict:
    """🟡 修复: 确定性 thread_id (keyword + platforms 的 SHA256)，不用 UUID。"""
    key = f"{keyword}|{','.join(sorted(platforms))}"
    thread_id = hashlib.sha256(key.encode()).hexdigest()[:16]
    return {"configurable": {"thread_id": thread_id}}


async def run_pipeline(
    keyword: str,
    *,
    limit: int = 30,
    platforms: list[str] | None = None,
    llm_filter: bool = False,
    pipeline_mode: str = "simple",
    analysis_mode: str = "keyword",
    sort_type: int | None = None,
    publish_time: int = 0,
    search_channel: str = "",
    include_raw: bool = False,
) -> dict:
    """运行 LangGraph 编排管道。

    pipeline_mode:
      "simple"    — 搜索→合并→格式化
      "full"      — 搜索→合并→7 Agent 分析链→下载→格式化
      "download"  — 搜索→合并→下载→格式化
      "sentiment" — 搜索→合并→舆情评论采集→格式化
    analysis_mode:
      "keyword" — 关键词搜索模式
      "account" — 对标账号模式（搜索→提取user_id→拉用户主页）
    """
    state = _build_initial_state(keyword, limit, platforms, llm_filter, pipeline_mode, analysis_mode,
                                 sort_type, publish_time, search_channel, include_raw)
    result = await compiled_graph.ainvoke(
        state,
        config=_make_config(keyword, platforms or _DEFAULT_PLATFORMS),
    )
    logger.info(f"pipeline [{pipeline_mode}] 完成: {len(result.get('final_output', []))} 条")

    # Optional: save task result to memory (RAG) — 默认关（settings.MEMORY_SAVE_ENABLED=False）
    if getattr(settings, "MEMORY_SAVE_ENABLED", False):
        try:
            from src.memory.recall import save_task_result
            final = result.get("final_output", [])
            summary = (
                f"Found {len(final)} items from {len(state.get('platforms', []))} platforms, "
                f"mode={pipeline_mode}, analysis={analysis_mode}."
            )
            save_task_result(
                keyword=keyword,
                summary=summary,
                metadata={
                    "final_count": len(final),
                    "platform_count": len(state.get("platforms", [])),
                    "pipeline_mode": pipeline_mode,
                    "analysis_mode": analysis_mode,
                },
            )
            logger.info(f"Memory: saved task '{keyword}' to Chroma")
        except Exception as exc:
            # Memory save 失败唔影响 pipeline 输出（graceful degradation）
            logger.warning(f"Memory save failed (non-fatal): {exc}")

    return result


async def run_pipeline_stream(
    keyword: str,
    *,
    limit: int = 30,
    platforms: list[str] | None = None,
    llm_filter: bool = False,
    pipeline_mode: str = "simple",
    analysis_mode: str = "keyword",
) -> AsyncIterator[dict]:
    """运行 LangGraph 编排管道（流式模式）。"""
    state = _build_initial_state(keyword, limit, platforms, llm_filter, pipeline_mode, analysis_mode)
    async for event in compiled_graph.astream_events(
        state,
        config=_make_config(keyword, platforms or _DEFAULT_PLATFORMS),
        version="v2",
    ):
        yield event
