"""Chroma 本地向量存储 — Smart Agent Pro 嘅「长期记忆」。

源：高强文《大模型项目实战》第 6 章 DB-GPT AWEL + 第 13 章 LlamaIndex 4 步索引。

设计：
- PersistentClient（落盘到 output/chroma/）
- Cosine similarity（HNSW index）
- 简单 add / query / count API
- Lazy load（首次调用 init Chroma client）
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

from src.memory.embeddings import encode_texts


_STORE_INSTANCE = None
_STORE_PATH: Optional[str] = None
_COLLECTION_NAME = "smart_agent_tasks"


def _default_path() -> str:
    """默认持久化路径。"""
    project_root = Path(__file__).resolve().parent.parent.parent
    return str(project_root / "output" / "chroma")


class MemoryStore:
    """Chroma 向量数据库封装（持久化到本地）。"""

    def __init__(self, path: Optional[str] = None, collection_name: str = _COLLECTION_NAME):
        """初始化 Chroma PersistentClient。

        Args:
            path: 持久化路径（默认 output/chroma/）
            collection_name: Collection 名（默认 smart_agent_tasks）
        """
        import chromadb

        self.path = path or os.environ.get("SMART_AGENT_CHROMA_PATH") or _default_path()
        Path(self.path).mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=self.path)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, doc_id: str, text: str, metadata: Optional[dict] = None) -> None:
        """添加一条记忆。

        Args:
            doc_id: 唯一 ID
            text: 文本内容（会 encode）
            metadata: 附加 metadata（dict）
        """
        embedding = encode_texts([text])[0]
        self.collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata or {}],
        )

    def query(self, text: str, n_results: int = 5) -> list[dict]:
        """语义检索。

        Args:
            text: 查询文本
            n_results: 返回 top-k

        Returns:
            [{"id": ..., "text": ..., "metadata": ..., "distance": ...}, ...]
        """
        if self.count() == 0:
            return []

        embedding = encode_texts([text])[0]
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=min(n_results, self.count()),
        )

        # Flatten results（Chroma 返 nested list）
        flat = []
        for i in range(len(results["ids"][0])):
            flat.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })
        return flat

    def count(self) -> int:
        """返回 Collection 文档数。"""
        return self.collection.count()

    def reset(self) -> None:
        """清空 collection（用于测试 / 重置）。"""
        try:
            self.client.delete_collection(self.collection.name)
        except Exception:
            pass  # collection 可能未存在
        self.collection = self.client.get_or_create_collection(
            name=self.collection.name,
            metadata={"hnsw:space": "cosine"},
        )


def get_store() -> MemoryStore:
    """Get singleton MemoryStore instance。"""
    global _STORE_INSTANCE
    if _STORE_INSTANCE is None:
        _STORE_INSTANCE = MemoryStore()
    return _STORE_INSTANCE