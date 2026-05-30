"""Smart Agent Evaluation Framework.

Phase C — 自动化评分 + LLM-as-Judge + Regression Test Runner.

Usage:
    python -m eval.runner              # 跑全部 regression tests
    python -m eval.runner TrendScout   # 只跑单个 agent
    python -m eval.judge               # 校准 LLM-as-Judge
"""

from eval.metrics import score_output
from eval.judge import LLMJudge
from eval.runner import run_all, run_agent

__all__ = ["score_output", "LLMJudge", "run_all", "run_agent"]
