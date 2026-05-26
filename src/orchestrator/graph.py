"""LangGraph StateGraph 定义 + 编译。

Mode:
  pipeline_mode="simple" — 搜索→合并→(LLM过滤→打分)→格式化  (Phase 1)
  pipeline_mode="full"   — 搜索→合并→7 Agent 分析链→格式化    (Phase 2)
"""
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from langgraph.checkpoint.memory import InMemorySaver
from src.orchestrator.state import PipelineState
from src.orchestrator.nodes import (
    search_platform,
    merge_results,
    llm_filter,
    llm_score,
    format_output,
)
from src.orchestrator.edges import route_after_merge as _route_simple
from src.utils.logger import logger


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


# ── Agent 节点函数 ──────────────────────────────────────────

_AGENT_FACTORY = {
    "trend_scout":      ("src.orchestrator.agents", "TrendScout"),
    "product_miner":    ("src.orchestrator.agents", "ProductMiner"),
    "video_analyst":    ("src.orchestrator.agents", "VideoAnalyst"),
    "sentiment_reader": ("src.orchestrator.agents", "SentimentReader"),
    "copy_writer":      ("src.orchestrator.agents", "CopyWriter"),
    "content_remixer":  ("src.orchestrator.agents", "ContentRemixer"),
    "pic_tactic":       ("src.orchestrator.agents", "PicTactic"),
}


async def _agent_node(state: PipelineState, agent_name: str) -> dict:
    """通用 Agent 节点：容错调用，单 Agent 失败不中断链路。"""
    mod_path, cls_name = _AGENT_FACTORY[agent_name]
    try:
        mod = __import__(mod_path, fromlist=[cls_name])
        agent_cls = getattr(mod, cls_name)
        return await agent_cls().as_node(state)
    except Exception as exc:
        logger.warning(f"Agent [{agent_name}] 失败，跳过: {exc}")
        return {}


def _make_agent_node(agent_name: str):
    """工厂函数：返回绑定 agent_name 的 node 函数。"""
    async def _node(state: PipelineState) -> dict:
        return await _agent_node(state, agent_name)
    return _node


# ── 路由函数 ────────────────────────────────────────────────

def _route_after_merge(state: PipelineState) -> str:
    """merge 后的路由：full 模式进 Agent 链，simple 模式走原有逻辑。"""
    if state.get("pipeline_mode") == "full":
        return "trend_scout"
    return _route_simple(state)


def _fanout_level1(state: PipelineState) -> list[Send]:
    """trend_scout 后并行分叉：选品 + 视频 + 情绪 同时分析。"""
    return [
        Send("product_miner", state),
        Send("video_analyst", state),
        Send("sentiment_reader", state),
    ]


def _fanout_level2(state: PipelineState) -> list[Send]:
    """分析完成后并行分叉：文案 + 改写 + 配图 同时生成。"""
    return [
        Send("copy_writer", state),
        Send("content_remixer", state),
        Send("pic_tactic", state),
    ]


async def _noop(state: PipelineState) -> dict:
    """同步点：等待所有并行分支完成。"""
    return {}


# ── Graph 构建 ──────────────────────────────────────────────

def build_graph() -> StateGraph:
    builder = StateGraph(PipelineState)

    # Phase 1 节点
    builder.add_node("search_one", _search_one)
    builder.add_node("merge_results", merge_results)
    builder.add_node("llm_filter", llm_filter)
    builder.add_node("llm_score", llm_score)
    builder.add_node("format_output", format_output)

    # Phase 2 Agent 节点（容错包装）
    for name in _AGENT_FACTORY:
        builder.add_node(name, _make_agent_node(name))

    # 同步点节点
    builder.add_node("_join_level1", _noop)

    # ── 边 ──────────────────────────────────────────────────

    # START → fanout search (5平台并行)
    builder.add_conditional_edges(START, _fanout_to_searchers, path_map=["search_one"])
    builder.add_edge("search_one", "merge_results")

    # merge → (trend_scout for full) or (llm_filter/format_output for simple)
    builder.add_conditional_edges(
        "merge_results",
        _route_after_merge,
        {
            "trend_scout": "trend_scout",
            "llm_filter": "llm_filter",
            "format_output": "format_output",
        },
    )

    # Phase 2: 两阶段并行 Agent 链
    # Stage 1: trend_scout → fanout (product_miner | video_analyst | sentiment_reader)
    builder.add_conditional_edges(
        "trend_scout", _fanout_level1,
        path_map=["product_miner", "video_analyst", "sentiment_reader"],
    )
    for node in ("product_miner", "video_analyst", "sentiment_reader"):
        builder.add_edge(node, "_join_level1")

    # Stage 2: join → fanout (copy_writer | content_remixer | pic_tactic)
    builder.add_conditional_edges(
        "_join_level1", _fanout_level2,
        path_map=["copy_writer", "content_remixer", "pic_tactic"],
    )
    for node in ("copy_writer", "content_remixer", "pic_tactic"):
        builder.add_edge(node, "format_output")

    # Phase 1: 原有 llm_filter/llm_score 路径
    builder.add_edge("llm_filter", "llm_score")
    builder.add_edge("llm_score", "format_output")

    # 终点
    builder.add_edge("format_output", END)

    return builder


def compile_graph():
    """编译 graph，带 InMemorySaver checkpointer。"""
    builder = build_graph()
    checkpointer = InMemorySaver()
    compiled = builder.compile(checkpointer=checkpointer)
    logger.info("LangGraph 编译完成")
    return compiled


# 模块级单例
compiled_graph = compile_graph()
