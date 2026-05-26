"""LangGraph 工作流状态定义。"""
from typing import Annotated, TypedDict


def _merge_dicts(a: dict, b: dict) -> dict:
    """合并两个 dict，用于并行分支结果聚合。"""
    merged = dict(a)
    merged.update(b)
    return merged


class PipelineState(TypedDict, total=False):
    keyword: str
    limit: int
    platforms: list[str]
    llm_filter: bool
    pipeline_mode: str           # "simple" | "full" — 控制是否运行 Agent 链
    search_results: Annotated[dict, _merge_dicts]   # {platform: [原始items]}
    merged_items: list[dict]      # 归一化 + L1去重后
    filtered_items: list[dict]    # LLM过滤后 (仅 llm_filter=True)
    scored_items: list[dict]      # LLM打分排序后 (仅 llm_filter=True)
    errors: Annotated[dict, _merge_dicts]            # {platform: error_msg}
    final_output: list[dict]
    # Agent 输出 (pipeline_mode="full" 时填充)
    trend_reports: dict           # {platform: TrendReport asdict}
    product_report: dict          # ProductReport asdict
    video_report: dict            # VideoReport asdict
    sentiment_report: dict        # SentimentReport asdict
    copy_report: dict             # CopyReport asdict
    remix_report: dict            # RemixReport asdict
    visual_report: dict           # VisualReport asdict