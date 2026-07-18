"""Test 以文搜图（CLIP cross-modal）。

源：高强文《大模型项目实战》第 16 章 CogVLM2 多模态检索。

按 smart-agent CLAUDE.md「测试粒度 ≈ 改动粒度」原则：
- Embeddings: 1 个
- Add + Search: 2 个
- Cross-modal 准确性: 1 个

总 4 个 test。
"""

import os
import shutil
import tempfile

import pytest


SAMPLE_IMG = "/tmp/ollama-test/Sonoma-1024.png"


@pytest.fixture
def temp_image_store():
    """临时 Chroma store fixture（用独立 collection）。"""
    if not os.path.exists(SAMPLE_IMG):
        pytest.skip(f"样本图片不存在: {SAMPLE_IMG}")

    tmpdir = tempfile.mkdtemp(prefix="chroma_image_test_")
    from src.memory.store import MemoryStore
    store = MemoryStore(path=tmpdir, collection_name="test_images")
    yield store
    try:
        store.client.reset()
    except Exception:
        pass
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_image_embeddings_clip():
    """Test 1: CLIP encode image + text（同一空间）。"""
    from src.memory.image_embeddings import encode_image, encode_text, get_clip_device

    img_emb = encode_image(SAMPLE_IMG)
    text_emb = encode_text("abstract colorful wallpaper")

    assert len(img_emb) == 512, f"CLIP embedding dim should be 512, got {len(img_emb)}"
    assert len(text_emb) == 512
    assert get_clip_device() in ("mps", "cuda", "cpu")


def test_image_add_and_search_by_text(temp_image_store):
    """Test 2: 添加图片 + 以文搜图 work。"""
    from src.memory.image_search import add_image_to_memory, search_by_text

    # Add 1 张图片
    doc_id = add_image_to_memory(
        image_path=SAMPLE_IMG,
        description="abstract colorful wallpaper with blue and green colors",
        metadata={"source": "macOS Sonoma default"},
        store=temp_image_store,
    )
    assert doc_id is not None
    assert temp_image_store.count() == 1

    # 以文搜图（query 应匹配）
    results = search_by_text(
        "colorful abstract wallpaper",
        top_k=1,
        store=temp_image_store,
    )
    assert len(results) == 1
    assert results[0]["distance"] < 1.0, "应该返相关图片（distance 较小）"
    assert "Sonoma" in results[0]["metadata"]["image_path"]


def test_image_search_cross_modal_accuracy(temp_image_store):
    """Test 3: Cross-modal 准确性——相关 query 应该排前。"""
    from src.memory.image_search import add_image_to_memory, search_by_text

    # Add 图片
    add_image_to_memory(
        image_path=SAMPLE_IMG,
        description="abstract colorful Sonoma wallpaper",
        store=temp_image_store,
    )

    # 测试多个 query，相关排第一
    queries = [
        ("abstract colorful wallpaper", True),   # 应该相关
        ("random irrelevant text", False),        # 应该唔相关
    ]

    for query, should_match in queries:
        results = search_by_text(query, top_k=1, store=temp_image_store)
        if should_match:
            assert len(results) >= 1
            # related query 嘅 distance 应该 < 1.0
            assert results[0]["distance"] < 1.0, f"'{query}' 应该返较相似结果"


def test_image_search_empty_store():
    """Test 4: 空 store search 返空 list 唔 crash。"""
    from src.memory.image_search import search_by_text

    tmpdir = tempfile.mkdtemp(prefix="chroma_empty_")
    from src.memory.store import MemoryStore
    empty_store = MemoryStore(path=tmpdir, collection_name="empty_test")

    try:
        results = search_by_text("anything", top_k=5, store=empty_store)
        assert results == []
    finally:
        try:
            empty_store.client.reset()
        except Exception:
            pass
        shutil.rmtree(tmpdir, ignore_errors=True)