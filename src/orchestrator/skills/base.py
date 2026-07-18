"""Skill 抽象基类 + Registry。

设计要点：
- Skill = Agent 嘅统一抽象（execute / to_tool_def）
- SkillRegistry = 全局注册表（按 name 查询）
- 唔强制迁移现有 Agent，向后兼容
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class Skill(ABC):
    """Agent 嘅统一抽象接口。

    实现要点：
      - name: 唯一标识（snake_case）
      - description: 一句话描述（for tool calling）
      - execute(state): 同步执行入口
      - to_tool_def(): 转成 OpenAI tool definition（供 LLM tool calling）
    """

    name: str = ""
    description: str = ""

    @abstractmethod
    async def execute(self, state: dict) -> dict:
        """执行 skill，返回 state update dict。

        Args:
            state: LangGraph PipelineState (or dict)

        Returns:
            state update dict (e.g., {"trend_report": {...}})
        """
        raise NotImplementedError

    def to_tool_def(self) -> dict:
        """转成 OpenAI tool definition，供 LLM tool calling 使用。

        默认实现：name + description + 空 parameters schema。
        子类可 override 提供更详细嘅 parameters。
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }


class SkillRegistry:
    """全局 Skill 注册表（单例模式）。

    Usage:
        from src.orchestrator.skills import registry

        # 注册
        registry.register(MySkill())

        # 查询
        skill = registry.get("trend_scout")

        # 列出全部
        all_skills = registry.list_all()

        # 转 OpenAI tools
        tools = registry.to_tool_defs()
    """

    def __init__(self):
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """注册 Skill。"""
        if not skill.name:
            raise ValueError(f"Skill {type(skill).__name__} 必须设置 name")
        if skill.name in self._skills:
            # 同名覆盖（warn 但允许）
            import warnings
            warnings.warn(f"Skill {skill.name} 已存在，将被覆盖")
        self._skills[skill.name] = skill

    def unregister(self, name: str) -> None:
        """取消注册。"""
        self._skills.pop(name, None)

    def get(self, name: str) -> Skill | None:
        """按 name 查询。"""
        return self._skills.get(name)

    def list_all(self) -> list[Skill]:
        """列出全部已注册 Skill。"""
        return list(self._skills.values())

    def list_names(self) -> list[str]:
        """列出全部 Skill name。"""
        return list(self._skills.keys())

    def to_tool_defs(self) -> list[dict]:
        """全部 Skill 转 OpenAI tool definitions（for tool calling）。"""
        return [s.to_tool_def() for s in self._skills.values()]