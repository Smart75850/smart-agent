"""MemGPT Long-term Layer — Chroma semantic recall（跨 session 知识）。

源：高强文《大模型项目实战》第 3 章 MemGPT 嘅 recall_storage。
     复用 src/memory/recall.py（之前 RAG 实现）。
"""

from __future__ import annotations
from typing import Optional

from src.memory.recall import (
    save_task_result as _save_task_result,
    recall_similar_tasks as _recall_similar_tasks,
    reset_memory as _reset_memory,
)


class LongTermLayer:
    """长期记忆层（cross-session knowledge）。

    复用 src/memory/recall.py 嘅 API（Chroma + sentence-transformers）。
    """

    def __init__(self, store=None):
        """初始化 long-term layer。

        Args:
            store: 可选嘅 MemoryStore（默认用 singleton）
        """
        self._store = store

    def write(self, keyword: str, summary: str, metadata: Optional[dict] = None) -> str:
        """写入长期记忆。

        Returns:
            doc_id
        """
        return _save_task_result(
            keyword=keyword,
            summary=summary,
            metadata=metadata,
            store=self._store,
        )

    def recall(self, keyword: str, top_k: int = 5) -> list[dict]:
        """Recall 同 keyword 相似嘅历史。"""
        return _recall_similar_tasks(keyword, top_k=top_k, store=self._store)

    def reset(self) -> None:
        """清空长期记忆（用于测试）。"""
        _reset_memory(self._store)