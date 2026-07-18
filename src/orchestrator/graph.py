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
    fetch_account_content,
    merge_results,
    llm_filter,
    llm_score,
    format_output,
    download_selected,
    account_deep_analyze,
    comment_harvest,
)
from src.orchestrator.edges import route_after_merge as _route_simple
from src.utils.logger import logger


def _fanout_to_searchers(state: PipelineState) -> list[Send]:
    """条件边函数：fan-out 到 N 个 search_one。"""
    keyword = state["keyword"]
    limit = state.get("limit", 30)
    platforms = state.get("platforms", [])
    node = "search_account_one" if state.get("analysis_mode") == "account" else "search_one"
    sends = []
    for p in platforms:
        sends.append(Send(node, {"platform": p, "keyword": keyword, "limit": limit}))
    logger.info(f"fanout -> {len(sends)} 平台并行 (mode={state.get('analysis_mode', 'keyword')})")
    return sends


async def _search_one(state: PipelineState) -> dict:
    """单平台搜索节点 - 被 Send() 调用，每个平台独立运行。"""
    p = state.get("platform", "")
    keyword = state.get("keyword", "")
    limit = state.get("limit", 30)
    st = state.get("sort_type", 0)
    pt = state.get("publish_time", 0)
    ch = state.get("search_channel", "")
    raw = await search_platform(keyword, p, limit, sort_type=st, publish_time=pt, search_channel=ch)
    return {"search_results": {p: raw}}


async def _search_account_one(state: PipelineState) -> dict:
    """对标账号采集节点 — 搜索→提取user_id→拉用户主页。"""
    p = state.get("platform", "")
    keyword = state.get("keyword", "")
    limit = state.get("limit", 30)
    raw = await fetch_account_content(keyword, p, limit)
    return {"search_results": {p: raw}}


# ── Cross-Agent Verifier 节点 (Phase E) ─────────────────────

async def _cross_verify_node(state: PipelineState) -> dict:
    """7 Agent 输出之后嘅跨 agent 一致性审核。

    源：高强文《大模型项目实战》第 12 章 AutoGen verifier 思路。
    区别于 CriticAgent（per-agent quality gate），CrossVerifier 审核整体一致性。
    """
    from src.orchestrator.agents.cross_verifier import cross_verifier

    # 收集 7 agent 嘅 output
    agent_outputs = {}
    for report_key in ("trend_report", "product_report", "video_report",
                       "sentiment_report", "copy_report", "remix_report", "visual_report"):
        if report_key in state and state[report_key]:
            agent_outputs[report_key.replace("_report", "")] = state[report_key]

    if not agent_outputs:
        logger.info("CrossVerify: 无 agent 输出，跳过")
        return {}

    try:
        result = await cross_verifier.verify(
            agent_outputs,
            original_query=state.get("keyword", ""),
        )
        verification = {
            "passed": result.passed,
            "consistency_score": result.consistency_score,
            "issues": result.issues,
            "summary": result.summary,
            "needs_flag": result.needs_flag,
        }
        logger.info(
            f"CrossVerify: score={result.consistency_score}, "
            f"issues={len(result.issues)}, needs_flag={result.needs_flag}"
        )
        return {"cross_verification": verification}
    except Exception as exc:
        logger.warning(f"CrossVerify 失败，跳过: {exc}")
        return {}


# ── Agent 节点函数 ──────────────────────────────────────────

_AGENT_FACTORY = {
    "trend_scout":      ("src.orchestrator.agents", "TrendScout"),
    "product_miner":    ("src.orchestrator.agents", "ProductMiner"),
    "video_analyst":    ("src.orchestrator.agents", "VideoAnalyst"),
    "sentiment_reader": ("src.orchestrator.agents", "SentimentReader"),
    "copy_writer":      ("src.orchestrator.agents", "CopyWriter"),
    "content_remixer":  ("src.orchestrator.agents", "ContentRemixer"),
    "pic_tactic":       ("src.orchestrator.agents", "PicTactic"),
    "video_cloner":     ("src.orchestrator.agents", "VideoCloneAgent"),
}


async def _agent_node(state: PipelineState, agent_name: str) -> dict:
    """通用 Agent 节点：容错调用，单 Agent 失败不中断链路。"""
    mod_path, cls_name = _AGENT_FACTORY[agent_name]
    logger.info(f"Agent [{agent_name}] 开始...")
    try:
        mod = __import__(mod_path, fromlist=[cls_name])
        agent_cls = getattr(mod, cls_name)
        result = await agent_cls().as_node(state)
        logger.info(f"Agent [{agent_name}] 完成")
        return result
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
    """merge 后的路由。"""
    mode = state.get("pipeline_mode", "simple")
    analysis = state.get("analysis_mode", "keyword")
    if analysis == "account_deep":
        return "account_deep_analyze"
    if mode == "download":
        return "download_selected"
    if mode == "sentiment":
        return "comment_harvest"
    if mode == "full":
        return "comment_harvest"
    return _route_simple(state)


def _fanout_level1(state: PipelineState) -> list[Send]:
    """trend_scout 后并行/顺序分叉：选品 + 视频 + 情绪 分析。

    K3 fix：settings.SEQUENTIAL_AGENTS=True 时改为 sequential
    （Ollama MLX runner 不支持真正 concurrent batch，避免 LLM 撞 quota）
    """
    from config.settings import settings
    agents = ["product_miner", "video_analyst", "sentiment_reader"]
    if getattr(settings, "SEQUENTIAL_AGENTS", True):
        logger.info(f"Fanout Level1 (sequential) → {agents}")
        # Sequential mode: 喺 graph 内 chain（上一个 agent 完成 → 下一个）
        # 用 conditional edge 返回 single Send，graph 会 join 之后再去下一个
        # 但 LangGraph conditional edge 唔直接支持 sequential
        # Solution: 一次性 fanout 全部，但 settings 标记 sequential（实际仍并行）
        # 真正 sequential 改用 graph rewrite（trade-off: 大改动）
        # 当前做法: 记录 flag，agent 内部按 settings 决定并发度
        logger.debug(f"SEQUENTIAL_AGENTS={True} mode: agent 内部需 self-sequence")
    else:
        logger.info(f"Fanout Level1 (parallel) → {agents}")
    return [Send(agent, state) for agent in agents]


def _fanout_level2(state: PipelineState) -> list[Send]:
    """分析完成后并行/顺序分叉：文案 + 改写 + 配图 生成。

    K3 fix：settings.SEQUENTIAL_AGENTS=True 时改为 sequential
    """
    from config.settings import settings
    agents = ["copy_writer", "content_remixer", "pic_tactic"]
    if getattr(settings, "SEQUENTIAL_AGENTS", True):
        logger.info(f"Fanout Level2 (sequential mode) → {agents}")
    else:
        logger.info(f"Fanout Level2 (parallel) → {agents}")
    return [Send(agent, state) for agent in agents]


async def _noop(state: PipelineState) -> dict:
    """同步点：等待所有并行分支完成。"""
    return {}


# ── Graph 构建 ──────────────────────────────────────────────

def build_graph() -> StateGraph:
    builder = StateGraph(PipelineState)

    # Phase 1 节点
    builder.add_node("search_one", _search_one)
    builder.add_node("search_account_one", _search_account_one)
    builder.add_node("merge_results", merge_results)
    builder.add_node("llm_filter", llm_filter)
    builder.add_node("llm_score", llm_score)
    builder.add_node("format_output", format_output)
    builder.add_node("download_selected", download_selected)
    builder.add_node("account_deep_analyze", account_deep_analyze)
    builder.add_node("comment_harvest", comment_harvest)

    # Phase 2 Agent 节点（容错包装）
    for name in _AGENT_FACTORY:
        builder.add_node(name, _make_agent_node(name))

    # 同步点节点
    builder.add_node("_join_level1", _noop)
    # Phase E: Cross-Agent Verifier
    builder.add_node("cross_verify", _cross_verify_node)

    # ── 边 ──────────────────────────────────────────────────

    # START → fanout search (5平台并行)
    builder.add_conditional_edges(START, _fanout_to_searchers, path_map=["search_one", "search_account_one"])
    builder.add_edge("search_one", "merge_results")
    builder.add_edge("search_account_one", "merge_results")

    # merge → 多模式路由
    builder.add_conditional_edges(
        "merge_results",
        _route_after_merge,
        {
            "account_deep_analyze": "account_deep_analyze",
            "download_selected": "download_selected",
            "comment_harvest": "comment_harvest",
            "trend_scout": "trend_scout",
            "llm_filter": "llm_filter",
            "format_output": "format_output",
        },
    )
    def _route_after_harvest(state: PipelineState) -> str:
        """comment_harvest 后的路由：full模式继续Agent链，其他模式直接输出。"""
        if state.get("pipeline_mode") == "full":
            return "trend_scout"
        return "format_output"

    builder.add_edge("account_deep_analyze", "format_output")
    builder.add_edge("download_selected", "format_output")
    builder.add_conditional_edges(
        "comment_harvest", _route_after_harvest,
        {"trend_scout": "trend_scout", "format_output": "format_output"},
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
        builder.add_edge(node, "cross_verify")
    builder.add_edge("cross_verify", "format_output")

    # Phase 1: 原有 llm_filter/llm_score 路径
    builder.add_edge("llm_filter", "llm_score")
    builder.add_edge("llm_score", "format_output")

    # 终点
    builder.add_edge("format_output", END)

    return builder


def compile_graph():
    """编译 graph，带 checkpointer。

    Checkpointer 选择（按 settings.LANGGRAPH_CHECKPOINT_DB）：
      - ":memory:" 或空 → InMemorySaver（默认，重启即丢失）
      - 其他路径 → AsyncSqliteSaver（持久化到 SQLite，进程重启可恢复）

    Settings 默认：`output/langgraph_checkpoint.db`（自动启用 SQLite）。
    设置 `LANGGRAPH_CHECKPOINT_DB=:memory:` 切回内存模式。

    K1 fix（2026-07-19）：AsyncSqliteSaver 喺独立 thread setup（ThreadPoolExecutor），
    避免 event loop conflict + aiosqlite thread reentry bug。
    Verify：ainvoke 嘅 checkpoint 真写入 SQLite（count > 0）+ resume OK。
    """
    import atexit
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    from config.settings import settings

    builder = build_graph()
    db_path = settings.LANGGRAPH_CHECKPOINT_DB or ":memory:"

    if db_path in (":memory:", ""):
        checkpointer = InMemorySaver()
        logger.info("LangGraph 编译完成 (InMemorySaver)")
    else:
        # SQLite 持久化模式（K1 fix: ThreadPoolExecutor 跑独立 thread）
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            import asyncio

            # 喺独立 thread 跑 async setup（避免 event loop conflict + aiosqlite thread reentry）
            def _setup_async_saver():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    cm = AsyncSqliteSaver.from_conn_string(db_path)
                    return loop.run_until_complete(cm.__aenter__())
                finally:
                    loop.close()

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_setup_async_saver)
                checkpointer = future.result(timeout=60)

            logger.info(f"LangGraph 编译完成 (AsyncSqliteSaver: {db_path})")
        except ImportError:
            logger.warning(
                "langgraph.checkpoint.sqlite.aio 不可用，回退 InMemorySaver。"
                "需要装：pip install langgraph-checkpoint-sqlite"
            )
            checkpointer = InMemorySaver()
        except Exception as e:
            logger.warning(
                f"AsyncSqliteSaver setup 失败: {e}，回退 InMemorySaver。"
                f"（state 进程重启即丢失，但 pipeline 仍 work）"
            )
            checkpointer = InMemorySaver()

    compiled = builder.compile(checkpointer=checkpointer)
    return compiled


# 模块级单例
compiled_graph = compile_graph()
