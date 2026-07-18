"""Test AWEL 3 层 Skill（Operator + Workflow DSL）。

源：高强文《大模型项目实战》第 6 章 DB-GPT AWEL。

按 smart-agent CLAUDE.md「测试粒度 ≈ 改动粒度」原则：
- Operator abstract: 1 个
- LLMOperator: 1 个
- Workflow DSL: 2 个（chain + multi-op）

总 4 个 test。
"""

import os
import pytest


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    """设置 Qwen proxy env vars + force reload settings module。"""
    import sys
    import importlib

    monkeypatch.setenv("LLM_API_URL", "http://127.0.0.1:11435/v1")
    monkeypatch.setenv("LLM_MODEL", "qwen3.6")
    monkeypatch.setenv("DEEPSEEK_API_URL", "http://127.0.0.1:11435/v1")
    monkeypatch.setenv("DEEPSEEK_MODEL", "qwen3.6")
    monkeypatch.setenv("QWEN_API_URL", "http://127.0.0.1:11435/v1")
    monkeypatch.setenv("QWEN_MODEL", "qwen3.6")

    # Force reload settings module（settings 系 module-level singleton，env vars 改了要重新 load）
    if "config.settings" in sys.modules:
        importlib.reload(sys.modules["config.settings"])
    yield


def test_operator_abstract():
    """Test 1: Operator 系 abstract class。"""
    from src.orchestrator.skills.operators import Operator

    # 不能直接实例化
    with pytest.raises(TypeError):
        Operator()


def test_llm_operator_real_call():
    """Test 2: LLMOperator 真实调 LLM（通过 proxy → Qwen3.6）。

    注意：Qwen3.6 thinking mode 需要 ≥ 2048 tokens，低于 2048 会撞 quota。
    """
    from src.orchestrator.skills.operators import LLMOperator

    op = LLMOperator(max_tokens=2048, temperature=0.5)

    async def run():
        result = await op.execute(prompt="用一句话介绍你自己")
        assert "response" in result
        assert len(result["response"]) > 5
        return result

    import asyncio
    result = asyncio.run(run())
    print(f"   LLM response: {result['response'][:100]}")


def test_workflow_chain_single_op():
    """Test 3: Workflow DSL 单个 operator work。"""
    from src.orchestrator.skills.operators import Workflow, LLMOperator

    workflow = Workflow("test_single").chain(LLMOperator(max_tokens=2048))

    async def run():
        result = await workflow.execute({"prompt": "说个数字"})
        assert "response" in result
        return result

    import asyncio
    result = asyncio.run(run())
    assert len(result["response"]) > 0


def test_workflow_chain_multi_ops():
    """Test 4: Workflow DSL 多个 operator chain + state 累积。"""
    from src.orchestrator.skills.operators import Workflow, LLMOperator, SummaryOperator

    # 链式：LLM → Summary（state 累积传递）
    workflow = (
        Workflow("test_chain")
        .chain(LLMOperator(max_tokens=4096))
        .chain(SummaryOperator(max_tokens=2048))
    )

    assert len(workflow) == 2

    async def run():
        result = await workflow.execute({
            "prompt": "简单介绍 Python 编程语言嘅 3 个特点",
        })
        assert "response" in result
        print(f"   Final response: {result['response'][:200]}")
        return result

    import asyncio
    result = asyncio.run(run())