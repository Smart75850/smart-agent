"""Memory 系统 — Smart Agent Pro 嘅「跨任务记忆」。

源：高强文《大模型项目实战》第 6 章 QAnything + 第 13 章 LlamaIndex + 第 16 章 CogVLM2。

提供：
- embeddings: 本地 sentence-transformers（中文友好，Apple Silicon MPS）
- store: Chroma 持久化向量库
- recall: 跨任务 recall API

设计原则（按 smart-agent CLAUDE.md）：
- Lazy loading：首次调用才加载 model（避免 import 延迟 11s）
- 本地优先：唔依赖 Ollama / 外部 API
- 向后兼容：现有 pipeline 唔强制集成（optional）
- 测试粒度 ≈ 改动粒度
"""

from src.memory.embeddings import (
    encode_texts,
    get_embedding_dim,
    get_embedding_device,
)
from src.memory.store import MemoryStore, get_store
from src.memory.recall import (
    save_task_result,
    recall_similar_tasks,
    reset_memory,
)

__all__ = [
    "encode_texts",
    "get_embedding_dim",
    "get_embedding_device",
    "MemoryStore",
    "get_store",
    "save_task_result",
    "recall_similar_tasks",
    "reset_memory",
]