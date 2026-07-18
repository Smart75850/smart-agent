"""Skill 系统 — Agent 抽象 + Registry。

源：高强文《大模型项目实战》第 6 章 DB-GPT AWEL 3 层架构（算子 / DSL / AgentFrame）。
目的：将 7 个 hardcoded Agent 抽象为统一 Skill 接口，支持：
  1. 动态注册（新增 agent 唔使改 graph.py）
  2. Tool calling 集成（Skill → OpenAI tool definition）
  3. Registry 模式（按 name 查询 + 列表化）

设计原则（按 smart-agent CLAUDE.md）：
  - Low-Hanging Fruit First：先抽象，唔强制迁移现有 7 agent
  - Explicit Uncertainty：现有 agent 仍系直接调用，Skill 系 optional 包装
  - Test 不要过设计：最小 Skill + Registry，加 1 个 demo
"""

from src.orchestrator.skills.base import Skill, SkillRegistry
from src.orchestrator.skills.demo_skill import DemoSkill

# 模块级注册表（懒加载，避免循环 import）
registry = SkillRegistry()

# 默认注册 demo skill
registry.register(DemoSkill())

__all__ = ["Skill", "SkillRegistry", "registry", "DemoSkill"]