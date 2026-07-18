"""LLMOperator — 调用 LLM 嘅算子（封装 base.py._call_llm）。

源：高强文《大模型项目实战》第 6 章 DB-GPT AWEL 算子层。

设计：
- 复用 BaseAgent 嘅 _call_llm（settings 嘅 LLM 配置）
- 支持 json_mode + max_tokens + temperature
- Operator 模式嘅 reference 实现
"""

from __future__ import annotations
from src.orchestrator.skills.operators.base import Operator
from src.orchestrator.agents.base import BaseAgent


class LLMOperator(Operator):
    """LLM 调用算子（封装 _call_llm）。"""

    name = "llm"
    description = "调用 LLM，返回生成文本（或 JSON）"

    def __init__(self, json_mode: bool = False, temperature: float = 0.7, max_tokens: int = 2048):
        self._agent = BaseAgent()
        self._json_mode = json_mode
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def execute(self, prompt: str = None, **kwargs) -> dict:
        """执行 LLM call。

        Args:
            prompt: 用户提示词

        Returns:
            {"response": str} 或 {"response": dict}（json_mode=True）
        """
        if prompt is None:
            prompt = kwargs.get("input", "")

        response = await self._agent._call_llm(
            prompt=prompt,
            temperature=kwargs.get("temperature", self._temperature),
            json_mode=kwargs.get("json_mode", self._json_mode),
            max_tokens=kwargs.get("max_tokens", self._max_tokens),
        )
        return {"response": response}


class SummaryOperator(Operator):
    """文本摘要算子（包装 LLMOperator，专门做 summarization）。"""

    name = "summary"
    description = "对文本做摘要"

    def __init__(self, max_tokens: int = 500):
        self._llm = LLMOperator(max_tokens=max_tokens, temperature=0.3)

    async def execute(self, text: str = None, **kwargs) -> dict:
        prompt = f"请用 100 字总结以下内容嘅核心要点：\n\n{text or kwargs.get('input', '')}"
        return await self._llm.execute(prompt=prompt)