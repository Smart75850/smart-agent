"""Rerank — Cross-encoder 两阶段检索嘅精排阶段。

源：高强文《大模型项目实战》第 6 章 QAnything 两阶段检索。
     Invariant #16: 向量粗排 + Cross-Encoder rerank 精排。

设计：
- Lazy load BAAI/bge-reranker-base（中文友好，~280MB）
- 接 Chroma 嘅 vector recall，做 cross-encoder 精排
- Optional（settings.RECALL_RERANK_ENABLED，默认关）
- 兼容现有 recall_similar_tasks API（如果 flag 关闭则跳过 rerank）
"""

from __future__ import annotations
import os
from typing import Optional


_RERANK_MODEL = None


def _load_rerank_model():
    """Lazy load cross-encoder rerank model。"""
    global _RERANK_MODEL
    if _RERANK_MODEL is not None:
        return _RERANK_MODEL

    from sentence_transformers import CrossEncoder

    model_name = os.environ.get(
        "SMART_AGENT_RERANK_MODEL",
        "BAAI/bge-reranker-base",
    )
    _RERANK_MODEL = CrossEncoder(model_name)
    return _RERANK_MODEL


def rerank(query: str, candidates: list[dict], top_k: Optional[int] = None) -> list[dict]:
    """Cross-encoder rerank 候选文档。

    Args:
        query: 查询文本
        candidates: 候选文档列表（来自 vector recall）
            每个 dict 应含 "text" 字段
        top_k: 返回 top-k（None = 全部返回，按 score 降序）

    Returns:
        候选文档按 rerank score 降序排列，每个 dict 加 "rerank_score" 字段
    """
    if not candidates:
        return []

    model = _load_rerank_model()

    # 构造 (query, doc) pairs
    pairs = [(query, c.get("text", "")) for c in candidates]

    # Cross-encoder scoring
    scores = model.predict(pairs)

    # 添加 score 到 candidates
    enriched = []
    for cand, score in zip(candidates, scores):
        enriched.append({**cand, "rerank_score": float(score)})

    # 按 score 降序
    enriched.sort(key=lambda x: x["rerank_score"], reverse=True)

    if top_k is not None:
        enriched = enriched[:top_k]

    return enriched