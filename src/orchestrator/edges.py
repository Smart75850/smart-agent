"""LangGraph 条件边路由。"""
from src.orchestrator.state import PipelineState


def route_after_merge(state: PipelineState) -> str:
    if state.get("llm_filter"):
        return "llm_filter"
    return "format_output"
