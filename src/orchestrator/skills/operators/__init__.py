"""AWEL 3 层架构 — 算子 + DSL + AgentFrame。

源：高强文《大模型项目实战》第 6 章 DB-GPT AWEL 3 层架构（算子 / DSL / AgentFrame）。

3 层：
1. **算子层 (Operator)**: 原子操作（LLMOperator / SummaryOperator）
2. **DSL 层**: Python fluent API（chain / execute）
3. **AgentFrame 层 (Workflow)**: 算子链式组合

设计原则（按 smart-agent CLAUDE.md）：
- 唔强制迁移现有 7 agent（向后兼容）
- demo operators + Workflow DSL 作为 reference
- 后续可逐步迁移现有 agent 到 Operator 模式
"""

from src.orchestrator.skills.operators.base import Operator
from src.orchestrator.skills.operators.llm_operator import LLMOperator, SummaryOperator
from src.orchestrator.skills.operators.workflow import Workflow

__all__ = [
    "Operator",
    "LLMOperator",
    "SummaryOperator",
    "Workflow",
]