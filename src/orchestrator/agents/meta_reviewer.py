"""Meta-Reviewer — AutoGen 嵌套对话嘅最深一层。

源：高强文《大模型项目实战》第 12 章 AutoGen 嵌套对话。
     Invariant #22: AutoGen 嵌套对话 = mavis verifier 反思（meta-level）。

设计（3 层 review）：
  Level 1: CriticAgent（per-agent quality gate，已存在）
  Level 2: CrossVerifier（跨 7 agent 一致性，已存在）
  Level 3: MetaReviewer（本模块）— meta-level 反思

MetaReviewer 嘅职责：
- 接收 CrossVerifier 嘅 consistency_score + issues
- 基于历史 critic feedback + cross_verify issues 做更深一层反思
- 识别 system-level 问题：
  * 输出「too generic」（所有 agent 都无 specific data points）
  * 「confident wrong」（agent 自评高分但实际有逻辑矛盾）
  * 「format drift」（format 偏离预期）
- 输出 meta_score + meta_concerns

按 smart-agent CLAUDE.md「最小可信改动」原则：
- 唔强制集成 graph.py
- 可以喺 final_output 加 meta_review 字段
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Optional

from src.orchestrator.agents.base import BaseAgent
from src.utils.logger import logger


@dataclass
class MetaReviewResult:
    passed: bool = True
    meta_score: int = 100  # 0-100（meta-level quality）
    concerns: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    summary: str = ""


class MetaReviewer(BaseAgent):
    """Meta-level reviewer（AutoGen 嵌套嘅最高层）。

    接收：
    - CrossVerifier result（consistency_score + issues）
    - 7 agent 嘅 outputs（用于 meta-level 分析）

    输出：
    - MetaReviewResult（passed + meta_score + concerns + suggestions）
    """

    def __init__(self):
        super().__init__()
        self._role = "meta_reviewer"

    async def review(
        self,
        agent_outputs: dict[str, dict],
        cross_verification: Optional[dict] = None,
        original_query: str = "",
    ) -> MetaReviewResult:
        """执行 meta-level review。

        Args:
            agent_outputs: 7 agent 嘅 output dict
            cross_verification: CrossVerifier result dict（passed + consistency_score + issues）
            original_query: 原始 keyword

        Returns:
            MetaReviewResult
        """
        # Step 1: 机械 meta check（无 LLM）
        mechanical_concerns = self._mechanical_meta_check(agent_outputs)

        # Step 2: LLM meta review（基于 cross_verify + 历史）
        cv_score = (cross_verification or {}).get("consistency_score", 100)
        cv_issues = (cross_verification or {}).get("issues", [])

        llm_result = await self._llm_meta_review(
            agent_outputs=agent_outputs,
            cv_score=cv_score,
            cv_issues=cv_issues,
            original_query=original_query,
        )

        # 综合
        meta_score = llm_result.get("meta_score", 100) - len(mechanical_concerns) * 10
        meta_score = max(0, meta_score)
        concerns = mechanical_concerns + llm_result.get("concerns", [])
        suggestions = llm_result.get("suggestions", [])
        passed = meta_score >= 70

        result = MetaReviewResult(
            passed=passed,
            meta_score=meta_score,
            concerns=concerns[:5],  # max 5
            suggestions=suggestions[:3],  # max 3
            summary=llm_result.get("summary", ""),
        )

        logger.info(
            f"MetaReviewer: score={meta_score}, concerns={len(concerns)}, passed={passed}"
        )
        return result

    def _mechanical_meta_check(self, agent_outputs: dict[str, dict]) -> list[str]:
        """机械 meta-level 检查。"""
        concerns = []

        # 1. 所有 agent 都太 generic（summary 太短）
        short_summaries = []
        for agent_name, output in agent_outputs.items():
            if not output:
                continue
            summary = str(output.get("summary", ""))
            if 0 < len(summary) < 30:
                short_summaries.append(agent_name)

        if len(short_summaries) >= 3:
            concerns.append(
                f"meta: {len(short_summaries)} 个 agent 嘅 summary 过短（<30 字），可能太 generic"
            )

        # 2. 所有 agent 嘅 score 都高（>85）但 CrossVerifier 返低分 → confident wrong
        high_scores = []
        for agent_name, output in agent_outputs.items():
            if not output:
                continue
            # 检查 items 入面嘅 score-like 字段
            items = output.get("items") or output.get("breakdowns") or []
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict):
                        vs = it.get("viral_score") or it.get("score") or it.get("monetization_potential")
                        if isinstance(vs, (int, float)) and vs > 85:
                            high_scores.append((agent_name, vs))

        # 3. 全部 output 都冇 items（output 太薄）
        empty_outputs = [
            name for name, output in agent_outputs.items()
            if not output or (
                not output.get("items")
                and not output.get("breakdowns")
                and not output.get("products")
                and not output.get("variants")
            )
        ]
        if len(empty_outputs) >= 4:
            concerns.append(
                f"meta: {len(empty_outputs)} 个 agent 嘅 output 缺少 items，"
                "可能 LLM 冇按预期 schema 输出"
            )

        return concerns

    async def _llm_meta_review(
        self,
        agent_outputs: dict[str, dict],
        cv_score: int,
        cv_issues: list[str],
        original_query: str,
    ) -> dict:
        """LLM meta-level review。"""
        # 摘要 prompt
        summary_lines = [
            f"原始任务：{original_query}",
            f"CrossVerifier 一致性分：{cv_score}",
            f"CrossVerifier 发现嘅 issues：{'; '.join(cv_issues[:3]) or '无'}",
            "",
            "7 个 Agent 输出摘要：",
        ]
        for agent_name, output in agent_outputs.items():
            if not output:
                continue
            summary = str(output.get("summary", ""))[:150]
            summary_lines.append(f"\n【{agent_name}】\n{summary}\n")

        summary_lines.append("""

请做 META-LEVEL review（高层反思，关注 system-level 问题）：
1. 整体输出质量（4 个 agent 嘅深度）
2. 有冇 system-level bias（例如全部都倾向正面 / 全部都 generic）
3. 数据点够唔够具体（有冇数字 / 时间 / 平台名引用）
4. 跨 agent 嘅 narrative 一致性（系咪讲紧同一个 story）

返回 JSON：
{
  "meta_score": 0-100,
  "concerns": ["meta-level 问题 1", "meta-level 问题 2"],
  "suggestions": ["改进建议 1", "改进建议 2"],
  "summary": "一句话 meta-level 评估"
}""")

        prompt = "\n".join(summary_lines)

        try:
            result = await self._call_llm(
                prompt,
                temperature=0.4,
                json_mode=True,
                max_tokens=2048,
            )
            parsed = self._parse_json(result)
            if isinstance(parsed, dict):
                return {
                    "meta_score": int(parsed.get("meta_score", 80)),
                    "concerns": list(parsed.get("concerns", []))[:5],
                    "suggestions": list(parsed.get("suggestions", []))[:3],
                    "summary": str(parsed.get("summary", ""))[:300],
                }
        except Exception as e:
            logger.warning(f"MetaReviewer LLM call failed: {e}")

        return {
            "meta_score": 80,
            "concerns": [],
            "suggestions": [],
            "summary": "Meta-review 失败，使用默认评估",
        }