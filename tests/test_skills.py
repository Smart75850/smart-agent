"""Test Skill 抽象 + Registry。"""

import asyncio

from src.orchestrator.skills import registry, Skill
from src.orchestrator.skills.demo_skill import DemoSkill


def test_registry_register_and_get():
    """测试注册 + 查询。"""
    s = DemoSkill()
    registry.register(s)
    assert registry.get("demo_skill") is s
    assert "demo_skill" in registry.list_names()


def test_registry_to_tool_defs():
    """测试转 OpenAI tool definitions。"""
    tools = registry.to_tool_defs()
    assert len(tools) >= 1
    demo_tool = next(t for t in tools if t["function"]["name"] == "demo_skill")
    assert "keyword" in demo_tool["function"]["parameters"]["properties"]


def test_skill_execute():
    """测试 Skill.execute 异步执行。"""

    async def run():
        skill = DemoSkill()
        result = await skill.execute({"keyword": "AI Agent"})
        assert "demo_output" in result
        assert "AI Agent" in result["demo_output"]
        return result

    result = asyncio.run(run())
    assert "DemoSkill 收到 keyword='AI Agent'" in result["demo_output"]


def test_skill_abstract_base():
    """测试 Skill 系 abstract class（唔可以直接 instantiate）。"""
    import pytest

    class IncompleteSkill(Skill):
        name = "incomplete"

        # 冇 override execute

    with pytest.raises(TypeError):
        IncompleteSkill()


def test_skill_registry_per_instance():
    """SkillRegistry 系普通 class（每次实例化独立 state）。"""
    from src.orchestrator.skills.base import SkillRegistry
    r1 = SkillRegistry()
    r2 = SkillRegistry()
    # 唔系 singleton（每次实例化独立）
    assert r1 is not r2
    # 唔共享 state
    r1.register(DemoSkill())
    assert r1.get("demo_skill") is not None
    assert r2.get("demo_skill") is None  # r2 唔受影响


def test_module_level_registry_singleton():
    """module-level `registry` 系 singleton（__init__.py 定义一次）。"""
    from src.orchestrator.skills import registry as r1
    from src.orchestrator.skills import registry as r2
    assert r1 is r2
    assert "demo_skill" in r1.list_names()  # 默认注册 DemoSkill