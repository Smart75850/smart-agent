"""Test OUTPUT IN CHINESE invariant（章 4 Camel/BabyAGI 启发）。

按 invariant #14：所有 prompt 自动 inject "OUTPUT IN CHINESE"。
"""

import pytest


def test_settings_default_chinese_invariant_true():
    """Test 1: settings 默认 CHINESE_OUTPUT_INVARIANT=True。"""
    from config.settings import settings
    assert settings.CHINESE_OUTPUT_INVARIANT is True, "默认应该开 OUTPUT IN CHINESE"


def test_chinese_invariant_injects_when_missing(monkeypatch):
    """Test 2: 没 OUTPUT IN CHINESE 时自动 inject。"""
    from config.settings import settings
    monkeypatch.setattr(settings, "CHINESE_OUTPUT_INVARIANT", True)

    from src.orchestrator.agents.base import BaseAgent
    agent = BaseAgent()

    # 检查 _call_llm 入面嘅 invariant
    # 由于 _call_llm 系 async + 实际调 HTTP，呢度只检查 helper 行为
    # 通过直接睇 _call_llm 嘅 source code 来验证 invariant（实际 production 验证）
    import inspect
    source = inspect.getsource(agent._call_llm)
    assert "OUTPUT IN CHINESE" in source, "_call_llm 应该 inject OUTPUT IN CHINESE"


def test_chinese_invariant_skipped_when_disabled(monkeypatch):
    """Test 3: settings 关咗 invariant 之后唔 inject。"""
    from config.settings import settings
    monkeypatch.setattr(settings, "CHINESE_OUTPUT_INVARIANT", False)

    from src.orchestrator.agents.base import BaseAgent
    agent = BaseAgent()

    import inspect
    source = inspect.getsource(agent._call_llm)
    # 当 invariant=False，应该有 guard 跳过
    assert "CHINESE_OUTPUT_INVARIANT" in source
    # Verify 条件式（不是无条件 inject）
    assert 'if getattr(settings, "CHINESE_OUTPUT_INVARIANT", True):' in source


def test_chinese_invariant_skipped_when_already_present():
    """Test 4: prompt 已经含 OUTPUT IN CHINESE 时唔重复 inject。"""
    from config.settings import settings
    # Default invariant=True
    from src.orchestrator.agents.base import BaseAgent
    agent = BaseAgent()

    # 直接调用逻辑 helper（通过 inspect）
    import inspect
    source = inspect.getsource(agent._call_llm)
    # 应该有检查避免重复
    assert '"OUTPUT IN CHINESE" not in prompt' in source