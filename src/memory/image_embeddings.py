"""Image Embeddings — CLIP cross-modal embedding。

源：高强文《大模型项目实战》第 16 章 CogVLM2 多模态检索。

设计：
- Lazy load sentence-transformers CLIP model
- encode_image(PIL.Image) → vector
- encode_text(str) → vector（同一空间，可做 cross-modal search）
- Apple Silicon MPS 加速
"""

from __future__ import annotations
import os
from typing import Optional, Union

import numpy as np
from PIL import Image


_CLIP_MODEL = None
_CLIP_DEVICE: Optional[str] = None


def _load_clip():
    """Lazy load CLIP model。"""
    global _CLIP_MODEL, _CLIP_DEVICE

    if _CLIP_MODEL is not None:
        return _CLIP_MODEL

    import torch
    from sentence_transformers import SentenceTransformer

    model_name = os.environ.get(
        "SMART_AGENT_CLIP_MODEL",
        "clip-ViT-B-32",
    )

    if torch.backends.mps.is_available():
        device = "mps"
    elif torch.cuda.is_available():
        device = "cuda"
    else:
        device = "cpu"

    _CLIP_MODEL = SentenceTransformer(model_name, device=device)
    _CLIP_DEVICE = device
    return _CLIP_MODEL


def encode_image(image: Union[str, Image.Image]) -> list[float]:
    """编码图片 → embedding vector。

    Args:
        image: PIL.Image 或文件路径

    Returns:
        512-dim embedding（clip-ViT-B-32）
    """
    model = _load_clip()
    if isinstance(image, str):
        image = Image.open(image)
    embedding = model.encode(image, normalize_embeddings=True)
    return embedding.tolist()


def encode_text(text: str) -> list[float]:
    """编码文本 → embedding vector（同一空间，可做以文搜图）。

    Args:
        text: 查询文本

    Returns:
        512-dim embedding（与 image embedding 同一空间）
    """
    model = _load_clip()
    embedding = model.encode([text], normalize_embeddings=True)
    return embedding[0].tolist()


def get_clip_device() -> str:
    """获取 CLIP 设备。"""
    _load_clip()
    return _CLIP_DEVICE