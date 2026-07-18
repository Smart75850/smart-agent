"""Workflow DSL — AWEL AgentFrame 层（算子链式组合）。

源：高强文《大模型项目实战》第 6 章 DB-GPT AWEL AgentFrame。

设计（minimal）：
- 简单 Python DSL：chain(operator) → chain(operator) → execute()
- 唔强制迁移现有 pipeline
- demo + reference 用
"""

from __future__ import annotations
from typing import Any

from src.orchestrator.skills.operators.base import Operator


class Workflow:
    """AWEL AgentFrame — 算子链式组合 DSL。

    Usage:
        workflow = Workflow()
        workflow.chain(LLMOperator()).chain(SummaryOperator())
        result = await workflow.execute(initial={"prompt": "..."})
    """

    def __init__(self, name: str = "workflow"):
        self.name = name
        self._operators: list[Operator] = []

    def chain(self, operator: Operator) -> "Workflow":
        """添加算子到 chain（fluent API）。"""
        self._operators.append(operator)
        return self

    async def execute(self, initial: dict | None = None) -> dict:
        """顺序执行所有 operator，state 累积传递。

        Args:
            initial: 初始 state dict

        Returns:
            最终 state dict（所有 operator 嘅 output 累积）
        """
        state: dict[str, Any] = dict(initial or {})
        for op in self._operators:
            # Operator 接收当前 state，返回 update
            update = await op.execute(**state)
            state.update(update)
        return state

    def __len__(self) -> int:
        return len(self._operators)

    def __repr__(self) -> str:
        ops = " → ".join(op.name for op in self._operators)
        return f"<Workflow {self.name}: {ops}>"