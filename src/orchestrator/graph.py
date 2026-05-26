"""LangGraph StateGraph 定义 + 编译。"""
from langgraph.graph import StateGraph, START, END
from langgraph.constants import Send
from langgraph.checkpoint.sqlite import SqliteSaver

from src.orchestrator.state import PipelineState
from src.orchestrator.nodes import (
    search_platform,
    merge_results,
    llm_filter,
    llm_score,
    format_output,
)
from src.orchestrator.edges import route_after_merge
from src.utils.logger import logger
from config.settings import settings


def _fanout_to_searchers(state: PipelineState) -> list[Send]:
    """条件边函数：fan-out 到 N 个 search_one。"""
    keyword = state["keyword"]
    limit = state.get("limit", 30)
    platforms = state.get("platforms", [])
    sends = []
    for p in platforms:
        sends.append(Send("search_one", {"platform": p, "keyword": keyword, "limit": limit}))
    logger.info(f"fanout -> {len(sends)} 平台并行")
    return sends


async def _search_one(state: PipelineState) -> dict:
    """单平台搜索节点 - 被 Send() 调用，每个平台独立运行。"""
    p = state.get("platform", "")
    keyword = state.get("keyword", "")
    limit = state.get("limit", 30)
    raw = await search_platform(keyword, p, limit)
    return {"search_results": {p: raw}}


def build_graph() -> StateGraph:
    builder = StateGraph(PipelineState)

    builder.add_node("search_one", _search_one)
    builder.add_node("merge_results", merge_results)
    builder.add_node("llm_filter", llm_filter)
    builder.add_node("llm_score", llm_score)
    builder.add_node("format_output", format_output)

    builder.add_conditional_edges(START, _fanout_to_searchers, path_map=["search_one"])
    builder.add_edge("search_one", "merge_results")
    builder.add_conditional_edges(
        "merge_results",
        route_after_merge,
        {"llm_filter": "llm_filter", "format_output": "format_output"},
    )
    builder.add_edge("llm_filter", "llm_score")
    builder.add_edge("llm_score", "format_output")
    builder.add_edge("format_output", END)

    return builder


def compile_graph():
    """编译 graph，带 SqliteSaver checkpointer。"""
    import os
    builder = build_graph()
    db_path = settings.LANGGRAPH_CHECKPOINT_DB
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    checkpointer = SqliteSaver.from_conn_string(db_path)
    compiled = builder.compile(checkpointer=checkpointer)
    logger.info("LangGraph 编译完成")
    return compiled


# 模块级单例
compiled_graph = compile_graph()