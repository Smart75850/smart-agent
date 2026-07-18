"""Recall API — Smart Agent Pro 嘅「跨任务 recall」。

源：高强文《大模型项目实战》第 6 章 QAnything 两阶段检索（向量 + rerank）。

设计（minimal）：
- 单阶段向量检索（Chroma cosine similarity）
- 预留 rerank 接口（未来加 cross-encoder）
- High-level API: recall_similar_tasks / save_task_result
"""

from __future__ import annotations
import hashlib
from datetime import datetime
from typing import Optional

from src.memory.store import MemoryStore


def _make_doc_id(keyword: str, timestamp: Optional[str] = None) -> str:
    """生成确定性 doc_id（keyword + timestamp）。"""
    ts = timestamp or datetime.now().isoformat()
    return hashlib.sha256(f"{keyword}|{ts}".encode()).hexdigest()[:16]


def save_task_result(
    keyword: str,
    summary: str,
    metadata: Optional[dict] = None,
    store: Optional[MemoryStore] = None,
) -> str:
    """保存一次 pipeline 任务结果到记忆库。

    Args:
        keyword: 搜索关键词
        summary: pipeline 嘅 final_output 摘要
        metadata: 附加 metadata（如 score / platform_count 等）
        store: 自定义 store（默认 singleton）

    Returns:
        doc_id（用于后续 recall / update）
    """
    store = store or MemoryStore()
    doc_id = _make_doc_id(keyword)
    text = f"关键词：{keyword}\n\n{summary}"

    full_metadata = {
        "keyword": keyword,
        "timestamp": datetime.now().isoformat(),
        **(metadata or {}),
    }

    store.add(doc_id=doc_id, text=text, metadata=full_metadata)
    return doc_id


def recall_similar_tasks(
    keyword: str,
    top_k: int = 5,
    store: Optional[MemoryStore] = None,
    rerank: bool = False,
    rerank_top_k: int = 20,
) -> list[dict]:
    """Recall 同 keyword 相似嘅历史任务（支持两阶段 rerank）。

    Args:
        keyword: 当前任务关键词
        top_k: 最终返回 top-k
        store: 自定义 store（默认 singleton）
        rerank: 是否启用 cross-encoder rerank（两阶段）
        rerank_top_k: 粗排 top-k（rerank 前嘅候选数）

    Returns:
        [{"id", "text", "metadata", "distance", "rerank_score?"}, ...]
    """
    from config.settings import settings

    store = store or MemoryStore()

    if store.count() == 0:
        return []

    # 决定是否启用 rerank
    enable_rerank = rerank or getattr(settings, "RECALL_RERANK_ENABLED", False)
    initial_k = rerank_top_k if enable_rerank else top_k

    # Stage 1: Vector recall（粗排）
    results = store.query(keyword, n_results=initial_k)

    if not enable_rerank or len(results) <= 1:
        return results[:top_k]

    # Stage 2: Cross-encoder rerank（精排）
    try:
        from src.memory.rerank import rerank as do_rerank
        reranked = do_rerank(keyword, results, top_k=top_k)
        return reranked
    except Exception as e:
        from src.utils.logger import logger
        logger.warning(f"Rerank failed, fallback to vector recall: {e}")
        return results[:top_k]


def reset_memory(store: Optional[MemoryStore] = None) -> None:
    """清空记忆库（用于测试 / 重置）。"""
    store = store or MemoryStore()
    store.reset()