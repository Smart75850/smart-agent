"""Test MemGPT 5 层（Long-term + Project layers）。

按 smart-agent CLAUDE.md「测试粒度 ≈ 改动粒度」原则：
- LongTermLayer: 2 个（write + recall）
- ProjectLayer: 3 个（write + list + summary）

总 5 个 test。
"""

import os
import shutil
import tempfile

import pytest


@pytest.fixture
def temp_stores():
    """临时 Chroma stores fixture。"""
    if not os.environ.get("SMART_AGENT_EMBED_MODEL"):
        os.environ["SMART_AGENT_EMBED_MODEL"] = "BAAI/bge-small-zh-v1.5"

    tmpdir = tempfile.mkdtemp(prefix="chroma_layers_test_")
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_long_term_write_and_recall(temp_stores):
    """Test 1: LongTermLayer write + recall work。"""
    from src.memory.layers import LongTermLayer
    from src.memory.store import MemoryStore

    store = MemoryStore(path=temp_stores, collection_name="test_lt")
    layer = LongTermLayer(store=store)

    layer.write("AI Agent", "2026 AI Agent 赛道分析...", {"score": 88})
    layer.write("美妆", "美妆视频增长 50%...", {"score": 92})

    assert store.count() == 2

    # Recall 同 keyword 相似嘅
    results = layer.recall("智能体", top_k=3)
    assert len(results) >= 1


def test_long_term_persists_across_instances(temp_stores):
    """Test 2: LongTermLayer 持久化（用同一 path）。"""
    from src.memory.layers import LongTermLayer
    from src.memory.store import MemoryStore

    # 第 1 个 instance
    store1 = MemoryStore(path=temp_stores, collection_name="test_persist")
    layer1 = LongTermLayer(store=store1)
    layer1.write("持久化测试", "test summary", {"score": 100})

    # 第 2 个 instance（应该可以读到）
    store2 = MemoryStore(path=temp_stores, collection_name="test_persist")
    layer2 = LongTermLayer(store=store2)
    results = layer2.recall("持久化", top_k=5)
    assert len(results) >= 1
    assert results[0]["text"]


def test_project_write_and_list(temp_stores):
    """Test 3: ProjectLayer write + list_runs work。"""
    from src.memory.layers import ProjectLayer
    from src.memory.store import MemoryStore

    store = MemoryStore(path=temp_stores, collection_name="test_project")
    layer = ProjectLayer(store=store)

    # 3 次 pipeline run 同 keyword
    layer.write_run("AI Agent", "run_001", "第一次分析：7 平台...")
    layer.write_run("AI Agent", "run_002", "第二次分析：发现新趋势...")
    layer.write_run("AI Agent", "run_003", "第三次分析：竞品更新...")
    layer.write_run("美妆", "run_004", "美妆分析...")

    assert store.count() == 4

    # List 同 keyword 嘅 run
    runs = layer.list_runs("AI Agent", top_k=10)
    assert len(runs) >= 3  # 至少有 3 个 AI Agent run


def test_project_summary_aggregation(temp_stores):
    """Test 4: ProjectLayer.get_project_summary 聚合数据。"""
    from src.memory.layers import ProjectLayer
    from src.memory.store import MemoryStore

    store = MemoryStore(path=temp_stores, collection_name="test_summary")
    layer = ProjectLayer(store=store)

    # 5 次 run 同 keyword
    for i in range(5):
        layer.write_run(
            "趋势分析",
            f"run_{i:03d}",
            f"第{i+1}次分析嘅摘要内容...",
        )

    summary = layer.get_project_summary("趋势分析")
    assert summary["keyword"] == "趋势分析"
    assert summary["run_count"] == 5
    assert summary["first_run"] is not None
    assert summary["latest_run"] is not None
    assert len(summary["summaries"]) == 5


def test_project_empty_keyword(temp_stores):
    """Test 5: 空 project list_runs + summary 都唔 crash。"""
    from src.memory.layers import ProjectLayer
    from src.memory.store import MemoryStore

    store = MemoryStore(path=temp_stores, collection_name="test_empty")
    layer = ProjectLayer(store=store)

    # Empty
    runs = layer.list_runs("不存在嘅 keyword", top_k=5)
    assert runs == []

    summary = layer.get_project_summary("不存在")
    assert summary["run_count"] == 0
    assert summary["summaries"] == []