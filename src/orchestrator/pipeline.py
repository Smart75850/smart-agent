"""高层 API — 一鸡两味（同步/流式）。"""
import hashlib
from typing import AsyncIterator

from src.orchestrator.state import PipelineState
from src.orchestrator.graph import compiled_graph
from src.utils.logger import logger

_DEFAULT_PLATFORMS = ["bilibili", "xiaohongshu", "douyin", "zhihu", "kuaishou"]


def _build_initial_state(
    keyword: str,
    limit: int,
    platforms: list[str] | None,
    llm_filter: bool,
    pipeline_mode: str = "simple",
) -> PipelineState:
    return {
        "keyword": keyword,
        "limit": limit,
        "platforms": platforms or _DEFAULT_PLATFORMS,
        "llm_filter": llm_filter,
        "pipeline_mode": pipeline_mode,
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
) -> dict:
    """运行 LangGraph 编排管道。

    pipeline_mode:
      "simple" — 搜索→合并→格式化
      "full"   — 搜索→合并→7 Agent 分析链→格式化
    """
    state = _build_initial_state(keyword, limit, platforms, llm_filter, pipeline_mode)
    result = await compiled_graph.ainvoke(
        state,
        config=_make_config(keyword, platforms or _DEFAULT_PLATFORMS),
    )
    logger.info(f"pipeline [{pipeline_mode}] 完成: {len(result.get('final_output', []))} 条")
    return result


async def run_pipeline_stream(
    keyword: str,
    *,
    limit: int = 30,
    platforms: list[str] | None = None,
    llm_filter: bool = False,
    pipeline_mode: str = "simple",
) -> AsyncIterator[dict]:
    """运行 LangGraph 编排管道（流式模式）。"""
    state = _build_initial_state(keyword, limit, platforms, llm_filter, pipeline_mode)
    async for event in compiled_graph.astream_events(
        state,
        config=_make_config(keyword, platforms or _DEFAULT_PLATFORMS),
        version="v2",
    ):
        yield event