"""Test Memory 模块（src/memory/）。

按 smart-agent CLAUDE.md「测试粒度 ≈ 改动粒度」原则：
- Embeddings: 1 个（核心）
- MemoryStore: 2 个（add/query + empty store）
- Recall API: 2 个（recall + save）

总 5 个 test。
"""

import os
import shutil
import tempfile

import pytest


@pytest.fixture
def temp_store():
    """临时 Chroma store fixture（test 完 cleanup）。"""
    tmpdir = tempfile.mkdtemp(prefix="chroma_test_")
    from src.memory.store import MemoryStore
    store = MemoryStore(path=tmpdir, collection_name="test_col")
    yield store
    # Cleanup
    try:
        store.client.reset()  # 清空 data
    except Exception:
        pass
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_embeddings_chinese():
    """Test 1: Embeddings encode 中文（中英文都 work）。"""
    from src.memory.embeddings import encode_texts, get_embedding_dim, get_embedding_device

    emb = encode_texts(["你好世界", "Hello world", "AI Agent"])
    dim = get_embedding_dim()
    device = get_embedding_device()

    assert len(emb) == 3, "Should return 3 embeddings"
    assert all(len(e) == dim for e in emb), f"All should have dim {dim}"
    assert dim > 0, f"dim should be positive, got {dim}"
    assert device in ("mps", "cuda", "cpu"), f"device should be valid, got {device}"
    # 不同句子应该有唔同 embedding
    assert emb[0] != emb[1], "Different sentences should have different embeddings"


def test_memory_store_add_and_query(temp_store):
    """Test 2: Store add + semantic query work。"""
    temp_store.add("id1", "美妆视频好火", {"score": 85})
    temp_store.add("id2", "编程教程热门", {"score": 78})
    temp_store.add("id3", "美食探店推荐", {"score": 92})

    assert temp_store.count() == 3

    # Query 同 id1 最相似
    results = temp_store.query("美妆化妆", n_results=2)
    assert len(results) == 2
    # 第一个应该系 "美妆视频好火"
    assert "美妆" in results[0]["text"] or "化妆" in results[0]["text"]
    # distance 应该按顺序递增
    assert results[0]["distance"] <= results[1]["distance"], "Results should be sorted by distance"


def test_memory_store_empty_query(temp_store):
    """Test 3: Empty store query 返空 list（唔 crash）。"""
    assert temp_store.count() == 0
    results = temp_store.query("anything", n_results=5)
    assert results == []


def test_save_task_result_and_recall(temp_store):
    """Test 4: save_task_result → recall_similar_tasks 闭环 work。"""
    from src.memory.recall import save_task_result, recall_similar_tasks

    # Save 3 task results
    save_task_result(
        keyword="AI Agent",
        summary="2026 年 AI Agent 赛道火热，主要分为通用型和垂直型。",
        metadata={"score": 88, "platform_count": 7},
        store=temp_store,
    )
    save_task_result(
        keyword="美妆视频",
        summary="美妆赛道 2026 增长 50%，爆款公式：3 秒钩子 + 测评。",
        metadata={"score": 92, "platform_count": 5},
        store=temp_store,
    )
    save_task_result(
        keyword="编程教程",
        summary="Python 教程流量稳定，主要受众为初学者。",
        metadata={"score": 75, "platform_count": 6},
        store=temp_store,
    )

    assert temp_store.count() == 3

    # Recall "AI Agent"
    results = recall_similar_tasks("智能体", top_k=3, store=temp_store)
    assert len(results) == 3
    # "AI Agent" 应该排第一（distance 最小）
    assert "AI Agent" in results[0]["metadata"].get("keyword", "") or "Agent" in results[0]["text"]
    # metadata 应包含 score
    assert "score" in results[0]["metadata"]


def test_reset_memory(temp_store):
    """Test 5: reset_memory 清空 store。"""
    from src.memory.recall import save_task_result, reset_memory

    save_task_result(
        keyword="test",
        summary="test summary",
        store=temp_store,
    )
    assert temp_store.count() == 1

    reset_memory(temp_store)
    assert temp_store.count() == 0