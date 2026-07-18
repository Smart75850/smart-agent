"""本地 embedding — BAAI/bge-small-zh-v1.5（中文友好，Apple Silicon MPS 加速）。

源：高强文《大模型项目实战》第 16 章 CogVLM2 用 `shibing624/text2vec-base-chinese`，
     第 6 章 QAnything 两阶段检索。

设计原则（按 smart-agent CLAUDE.md）：
- Lazy loading：首次调用才加载 model（避免 import 时 11s 延迟）
- 本地优先：唔依赖 Ollama / 外部 API
- 中文优先：bge-small-zh 系中文 SOTA 小模型（512 dim, 93MB）
"""

from __future__ import annotations
import os
from typing import Optional


_EMBEDDING_MODEL = None  # Lazy singleton
_EMBEDDING_DIM: Optional[int] = None
_EMBEDDING_DEVICE: Optional[str] = None


def _load_model():
    """Lazy load embedding model。"""
    global _EMBEDDING_MODEL, _EMBEDDING_DIM, _EMBEDDING_DEVICE

    if _EMBEDDING_MODEL is not None:
        return _EMBEDDING_MODEL

    import torch
    from sentence_transformers import SentenceTransformer

    model_name = os.environ.get(
        "SMART_AGENT_EMBED_MODEL",
        "BAAI/bge-small-zh-v1.5"
    )

    # 优先 MPS（Apple Silicon），否则 CPU
    if torch.backends.mps.is_available():
        device = "mps"
    elif torch.cuda.is_available():
        device = "cuda"
    else:
        device = "cpu"

    _EMBEDDING_MODEL = SentenceTransformer(model_name, device=device)
    _EMBEDDING_DIM = _EMBEDDING_MODEL.get_embedding_dimension()
    _EMBEDDING_DEVICE = device

    return _EMBEDDING_MODEL


def encode_texts(texts: list[str]) -> list[list[float]]:
    """编码文本列表 → embedding vectors。

    Args:
        texts: 文本列表（中文 / 英文 / mixed 都 work）

    Returns:
        list of embedding vectors（每个 512-dim）
    """
    model = _load_model()
    embeddings = model.encode(texts, normalize_embeddings=True)
    return embeddings.tolist()


def get_embedding_dim() -> int:
    """获取 embedding 维度（lazy load 触发）。"""
    _load_model()
    return _EMBEDDING_DIM


def get_embedding_device() -> str:
    """获取 embedding 设备（mps / cuda / cpu）。"""
    _load_model()
    return _EMBEDDING_DEVICE