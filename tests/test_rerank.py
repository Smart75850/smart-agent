"""Test Rerank 集成（两阶段检索）。

源：高强文《大模型项目实战》第 6 章 QAnything。

按 smart-agent CLAUDE.md「测试粒度 ≈ 改动粒度」原则：
- Rerank basic: 1 个
- Rerank with vector recall: 1 个
- Settings toggle: 1 个

总 3 个 test。
"""

import os
import shutil
import sys
import tempfile

import pytest


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    """设置 env vars + reload settings。"""
    monkeypatch.setenv("LLM_API_URL", "http://127.0.0.1:11435/v1")
    monkeypatch.setenv("LLM_MODEL", "qwen3.6")
    monkeypatch.setenv("DEEPSEEK_API_URL", "http://127.0.0.1:11435/v1")
    monkeypatch.setenv("DEEPSEEK_MODEL", "qwen3.6")
    if "config.settings" in sys.modules:
        import importlib
        importlib.reload(sys.modules["config.settings"])


def test_rerank_basic():
    """Test 1: Rerank 基本工作（query + docs → ranked docs）。"""
    from src.memory.rerank import rerank

    query = "美妆视频爆款"
    candidates = [
        {"id": "1", "text": "美妆教程：3 秒钩子 + 测评 + CTA"},
        {"id": "2", "text": "Python 编程入门"},
        {"id": "3", "text": "美妆品牌种草笔记"},
        {"id": "4", "text": "美食探店推荐"},
    ]

    results = rerank(query, candidates, top_k=2)
    assert len(results) == 2
    # 应该有 rerank_score
    assert "rerank_score" in results[0]
    # 相关文档应该排前（"美妆" 嘅 2 个）
    relevant_count = sum(1 for r in results if "美妆" in r["text"])
    assert relevant_count >= 1, f"Top-2 应该有 ≥1 个相关，但得 {relevant_count}"


def test_recall_with_rerank():
    """Test 2: recall_similar_tasks 两阶段检索 work。"""
    from src.memory.store import MemoryStore
    from src.memory.recall import recall_similar_tasks

    tmpdir = tempfile.mkdtemp(prefix="chroma_rerank_test_")
    try:
        store = MemoryStore(path=tmpdir, collection_name="test_rerank")
        # Add 几个文档
        store.add("1", "美妆教程：3 秒钩子 + 测评 + CTA", {"score": 85})
        store.add("2", "Python 编程入门教程", {"score": 70})
        store.add("3", "美妆品牌种草笔记", {"score": 92})
        store.add("4", "美食探店推荐", {"score": 78})

        # 启用 rerank
        results = recall_similar_tasks(
            "美妆视频",
            top_k=2,
            store=store,
            rerank=True,
        )
        assert len(results) == 2
        # 应该有 rerank_score
        assert "rerank_score" in results[0]
        print(f"   Reranked top-2: {[(r['text'][:30], r['rerank_score']) for r in results]}")
    finally:
        try:
            store.client.reset()
        except Exception:
            pass
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_recall_rerank_disabled():
    """Test 3: 默认 recall 唔做 rerank（向后兼容）。"""
    from src.memory.store import MemoryStore
    from src.memory.recall import recall_similar_tasks

    tmpdir = tempfile.mkdtemp(prefix="chroma_norerank_test_")
    try:
        store = MemoryStore(path=tmpdir, collection_name="test_norerank")
        store.add("1", "美妆视频", {"score": 85})

        # Default: 唔 rerank
        results = recall_similar_tasks("美妆", top_k=1, store=store)
        assert len(results) == 1
        # 应该冇 rerank_score（向后兼容）
        assert "rerank_score" not in results[0]
    finally:
        try:
            store.client.reset()
        except Exception:
            pass
        shutil.rmtree(tmpdir, ignore_errors=True)