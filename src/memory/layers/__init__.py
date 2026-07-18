"""MemGPT 5 层虚拟上下文 — Smart Agent Pro 嘅「记忆分层体系」。

源：高强文《大模型项目实战》第 3 章 MemGPT（virtual context management）。
     Invariant #13: MemGPT 虚拟上下文 = mavis 5 层记忆。

5 层设计：
1. **short_term**: 当前 LangGraph PipelineState（in-memory, per pipeline run）
2. **long_term**: Chroma 向量库（跨 session 知识，semantic recall）
3. **task**: 当前 task 嘅 metadata + dependencies
4. **reflection**: Critic 历史反馈（来自 trace_collector + cross_verifier）
5. **project**: 同 keyword 累积（多次跑同一 topic 嘅结果聚合）

设计原则（按 smart-agent CLAUDE.md）：
- 复用现有架构（短期/任务/反思已存在）
- 新增 2 层（长期 + 项目）即可（之前 RAG 已实现长期）
- 向后兼容：未启用时 fallback 到无 layer 模式
"""

from src.memory.layers.long_term import LongTermLayer
from src.memory.layers.project import ProjectLayer

__all__ = [
    "LongTermLayer",
    "ProjectLayer",
]