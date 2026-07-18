"""Test Meta-Reviewer（AutoGen 嵌套 deepest level）。

源：高强文《大模型项目实战》第 12 章 AutoGen 嵌套对话。

按 smart-agent CLAUDE.md「测试粒度 ≈ 改动粒度」原则：
- Mechanical meta check: 1 个
- LLM meta review: 1 个
- 3 层 review 集成: 1 个

总 3 个 test。
"""

import os
import sys

import pytest


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    """设置 Qwen proxy env vars + force reload settings module。"""
    monkeypatch.setenv("LLM_API_URL", "http://127.0.0.1:11435/v1")
    monkeypatch.setenv("LLM_MODEL", "qwen3.6")
    monkeypatch.setenv("DEEPSEEK_API_URL", "http://127.0.0.1:11435/v1")
    monkeypatch.setenv("DEEPSEEK_MODEL", "qwen3.6")
    monkeypatch.setenv("QWEN_API_URL", "http://127.0.0.1:11435/v1")
    monkeypatch.setenv("QWEN_MODEL", "qwen3.6")
    if "config.settings" in sys.modules:
        import importlib
        importlib.reload(sys.modules["config.settings"])
    yield


def test_meta_reviewer_mechanical_check():
    """Test 1: 机械 meta check 能识别 system-level 问题。"""
    from src.orchestrator.agents.meta_reviewer import MetaReviewer

    reviewer = MetaReviewer()

    # 模拟：4 个 agent 嘅 summary 过短（generic）
    bad_outputs = {
        "trend": {"summary": "hi"},  # 太短
        "sentiment": {"summary": "ok"},  # 太短
        "copy": {"summary": "fine"},  # 太短
        "product": {"summary": "good"},  # 太短
    }

    async def run():
        result = await reviewer.review(bad_outputs, cross_verification={"consistency_score": 80, "issues": []})
        # 应该有 mechanical concern（summary 过短）
        assert any("summary" in c.lower() for c in result.concerns), \
            f"应该检测到 summary 过短，但 concerns = {result.concerns}"
        return result

    import asyncio
    result = asyncio.run(run())
    print(f"   Meta score: {result.meta_score}, concerns: {result.concerns}")


def test_meta_reviewer_quality_outputs():
    """Test 2: 高质量输出 → meta_score 高。"""
    from src.orchestrator.agents.meta_reviewer import MetaReviewer

    reviewer = MetaReviewer()

    good_outputs = {
        "trend": {
            "summary": "2026 年 AI Agent 赛道火热，主要分为通用型（CrewAI / LangGraph）和垂直型（Devika / CodeFuse）...",
            "items": [{"viral_score": 78, "category": "AI工具"}],
        },
        "sentiment": {
            "summary": "用户对 AI Agent 接受度高（正面 78%），主要关注数据隐私 + 成本...",
            "items": [{"positive_pct": 78, "negative_pct": 12}],
        },
        "copy": {
            "summary": "针对自媒体创作者嘅 AI Agent 营销文案，3 个不同风格...",
            "items": [{"text": "..."}],
        },
    }

    async def run():
        result = await reviewer.review(good_outputs, cross_verification={"consistency_score": 95, "issues": []})
        # 高质量 + 高 consistency → meta_score 应该高
        assert result.meta_score >= 70, f"高质量输出应该有高 meta_score，但得 {result.meta_score}"
        return result

    import asyncio
    result = asyncio.run(run())
    print(f"   Meta score: {result.meta_score}, passed: {result.passed}")


def test_meta_reviewer_3layer_integration():
    """Test 3: 三层 review pipeline（per-agent → cross → meta）end-to-end。"""
    from src.orchestrator.agents.meta_reviewer import MetaReviewer
    from src.orchestrator.agents.cross_verifier import cross_verifier

    # Mock outputs
    outputs = {
        "trend": {"summary": "AI Agent 趋势分析 2026..."},
        "sentiment": {"summary": "用户情感分析：正面 70%..."},
    }

    async def run():
        # Layer 2: cross-verify
        cv_result = await cross_verifier.verify(outputs, original_query="AI Agent")

        # Layer 3: meta-review（基于 cross_verify result）
        reviewer = MetaReviewer()
        meta_result = await reviewer.review(
            outputs,
            cross_verification={
                "consistency_score": cv_result.consistency_score,
                "issues": cv_result.issues,
            },
            original_query="AI Agent",
        )

        assert meta_result.meta_score >= 0
        print(f"   CV score: {cv_result.consistency_score} → Meta score: {meta_result.meta_score}")
        return meta_result

    import asyncio
    asyncio.run(run())