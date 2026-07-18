"""Operator 抽象 — AWEL 算子层（最低层）。

源：高强文《大模型项目实战》第 6 章 DB-GPT AWEL 3 层架构。
     算子层 = LLM 应用操作原子（LLM call / search / filter 等）。

设计（按 smart-agent CLAUDE.md 最小可信改动）：
- Operator = 单一 async 任务嘅 abstract
- 唔强制迁移现有 7 agent
- demo operators 提供 reference
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class Operator(ABC):
    """AWEL 算子 — 单一原子操作。"""

    name: str = ""
    description: str = ""

    @abstractmethod
    async def execute(self, **kwargs) -> dict:
        """执行算子，返回 state update dict。"""
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<Operator {self.name}: {self.description}>"