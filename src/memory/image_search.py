"""Image Search API — 以文搜图（CogVLM2 风格）。

源：高强文《大模型项目实战》第 16 章 CogVLM2 多模态检索。

设计：
- 复用 MemoryStore（Chroma 持久化）
- 不同 collection（避免与 text memory 混淆）
- by_text API：输入文本，返最相似嘅 image
- by_image API：输入图片，返相似图片
- add_image：添加图片到 memory
"""

from __future__ import annotations
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from PIL import Image

from src.memory.store import MemoryStore
from src.memory.image_embeddings import encode_image, encode_text


_IMAGES_COLLECTION = "smart_agent_images"


def _image_doc_id(image_path: str) -> str:
    """生成确定性 doc_id（用文件路径）。"""
    return hashlib.sha256(image_path.encode()).hexdigest()[:16]


def add_image_to_memory(
    image_path: str,
    description: str = "",
    metadata: Optional[dict] = None,
    store: Optional[MemoryStore] = None,
) -> str:
    """添加图片到 memory（含 description 用于 fallback search）。

    Args:
        image_path: 图片文件路径
        description: 图片描述（可选，for text-only fallback）
        metadata: 附加 metadata
        store: 自定义 store

    Returns:
        doc_id
    """
    store = store or MemoryStore(collection_name=_IMAGES_COLLECTION)

    # 编码 image embedding
    embedding = encode_image(image_path)

    # 写入 Chroma（document = description + path，方便 fallback search）
    doc_id = _image_doc_id(image_path)
    text = description or f"图片路径：{image_path}"

    full_metadata = {
        "image_path": image_path,
        "description": description,
        "timestamp": datetime.now().isoformat(),
        **(metadata or {}),
    }

    # MemoryStore.add 接受 doc_id / text / metadata，embedding 由 store.encode 提供
    # 但我哋要 override 用 CLIP embedding 而唔系 sentence-transformers text embedding
    # 直接用 Chroma client
    store.collection.add(
        ids=[doc_id],
        embeddings=[embedding],
        documents=[text],
        metadatas=[full_metadata],
    )

    return doc_id


def search_by_text(
    query: str,
    top_k: int = 5,
    store: Optional[MemoryStore] = None,
) -> list[dict]:
    """以文搜图。

    Args:
        query: 文本查询（例如「蓝色海洋 wallpaper」）
        top_k: 返回 top-k
        store: 自定义 store

    Returns:
        [{"id", "text", "metadata", "distance"}, ...]
    """
    store = store or MemoryStore(collection_name=_IMAGES_COLLECTION)

    if store.count() == 0:
        return []

    # 编码 query（用 CLIP text encoder，跨模态到 image space）
    embedding = encode_text(query)

    results = store.collection.query(
        query_embeddings=[embedding],
        n_results=min(top_k, store.count()),
    )

    # Flatten
    flat = []
    for i in range(len(results["ids"][0])):
        flat.append({
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
        })
    return flat


def search_by_image(
    image_path: str,
    top_k: int = 5,
    store: Optional[MemoryStore] = None,
) -> list[dict]:
    """以图搜图（similar image search）。

    Args:
        image_path: 查询图片路径
        top_k: 返回 top-k
        store: 自定义 store

    Returns:
        [{"id", "text", "metadata", "distance"}, ...]
    """
    store = store or MemoryStore(collection_name=_IMAGES_COLLECTION)

    if store.count() == 0:
        return []

    # 用 image embedding 查 image collection
    embedding = encode_image(image_path)

    results = store.collection.query(
        query_embeddings=[embedding],
        n_results=min(top_k, store.count()),
    )

    flat = []
    for i in range(len(results["ids"][0])):
        flat.append({
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
        })
    return flat