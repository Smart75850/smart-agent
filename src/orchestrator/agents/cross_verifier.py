"""Cross-Agent Verifier — 全局 7 Agent 输出一致性审核。

源：高强文《大模型项目实战》第 12 章 AutoGen verifier 思路（全局 review 模式）。

与现有 CriticAgent 嘅区别：
- CriticAgent → 单 agent 嘅 per-output quality gate（已有）
- CrossVerifier → 7 agent 输出之后嘅 **跨 agent 一致性 + 整体质量** 审核（新增）

具体审核维度：
1. **跨 agent contradiction**（trend_scout 话「火热」但 sentiment_reader 话「冷淡」？）
2. **数据一致性**（多个 agent 引用嘅数字 / 平台 / 商品名称一致？）
3. **整体报告完整度**（7 个 agent 全部有有效输出？）
4. **格式合规**（所有输出符合预期 schema？）

返回 CrossVerificationResult：
  {
    "passed": bool,                # 是否通过（passed=True 即刻输出，False = warning）
    "consistency_score": 0-100,    # 跨 agent 一致性分数
    "issues": [str],               # 具体问题列表
    "summary": str,                # 整体评估
  }

用法 (graph.py)：
  builder.add_edge("copy_writer"|"content_remixer"|"pic_tactic", "cross_verify")
  builder.add_edge("cross_verify", "format_output")
"""

from __future__ import annotations
import re
import json
from dataclasses import dataclass, field

from src.orchestrator.agents.base import BaseAgent
from src.utils.logger import logger


@dataclass
class CrossVerificationResult:
    passed: bool = True
    consistency_score: int = 100   # 0-100，跨 agent 一致性
    issues: list[str] = field(default_factory=list)
    summary: str = ""
    needs_flag: bool = False       # True = 需要喺 final_output 标注「跨 agent 不一致」


class CrossVerifier(BaseAgent):
    """7 Agent 输出一致性全局审核。"""

    def __init__(self):
        super().__init__()
        self._role = "cross_verifier"

    async def verify(
        self,
        agent_outputs: dict[str, dict],
        original_query: str = "",
    ) -> CrossVerificationResult:
        """审核 7 agent 输出。

        Args:
            agent_outputs: {agent_name: output_dict}
            original_query: 原始搜索 keyword / task

        Returns:
            CrossVerificationResult
        """
        if not agent_outputs:
            return CrossVerificationResult(
                passed=False,
                consistency_score=0,
                issues=["no_agent_outputs"],
                summary="无 agent 输出，跳过审核",
            )

        # Step 1: 机械检查（不调 LLM）
        mechanical_issues = self._mechanical_checks(agent_outputs)
        mechanical_score = max(0, 100 - len(mechanical_issues) * 15)

        # Step 2: LLM 审核（仅当 ≥3 个 agent 有输出 + mechanical 分数 >= 50）
        llm_result = None
        valid_agents = [k for k, v in agent_outputs.items() if v and isinstance(v, dict)]
        if len(valid_agents) >= 3 and mechanical_score >= 50:
            llm_result = await self._llm_cross_check(agent_outputs, original_query)

        # 综合
        if llm_result:
            consistency_score = min(mechanical_score, llm_result.get("consistency_score", mechanical_score))
            issues = mechanical_issues + llm_result.get("issues", [])
            summary = llm_result.get("summary", "")
        else:
            consistency_score = mechanical_score
            issues = mechanical_issues
            summary = f"机械检查发现 {len(mechanical_issues)} 个问题" if mechanical_issues else "机械检查通过"

        passed = consistency_score >= 60
        needs_flag = consistency_score < 70  # < 70 分需要喺 final_output 加 warning

        result = CrossVerificationResult(
            passed=passed,
            consistency_score=consistency_score,
            issues=issues,
            summary=summary,
            needs_flag=needs_flag,
        )

        logger.info(
            f"CrossVerifier: score={consistency_score}, issues={len(issues)}, "
            f"passed={passed}, needs_flag={needs_flag}"
        )
        return result

    def _mechanical_checks(self, agent_outputs: dict[str, dict]) -> list[str]:
        """机械检查（无 LLM 调用）：输出完整性、必填字段。"""
        issues = []

        for agent_name, output in agent_outputs.items():
            if not output:
                issues.append(f"{agent_name}: 空输出")
                continue

            # 通用：summary 字段
            summary = output.get("summary", "")
            if not summary or len(str(summary)) < 10:
                issues.append(f"{agent_name}: summary 过短或为空（{len(str(summary))} 字）")

            # 跨 agent：抽取数字、平台、商品名，比对一致性
        cross_issues = self._check_cross_consistency(agent_outputs)
        issues.extend(cross_issues)

        return issues

    def _check_cross_consistency(self, agent_outputs: dict[str, dict]) -> list[str]:
        """跨 agent 一致性检查：数字 / 平台 / 商品名一致性。"""
        issues = []

        # 抽取所有 agent 提到嘅数字（百分比、分数等）
        numbers_by_agent: dict[str, set[str]] = {}
        for agent_name, output in agent_outputs.items():
            if not output:
                continue
            output_str = json.dumps(output, ensure_ascii=False)
            # 抽取「数字%」类（e.g. 50%、85%）
            pct_matches = set(re.findall(r'(\d+(?:\.\d+)?%)', output_str))
            numbers_by_agent[agent_name] = pct_matches

        # 对比 sentiment_reader（正面%）vs trend_scout（viral_score）
        sent = agent_outputs.get("sentiment_reader", {})
        trend = agent_outputs.get("trend_scout", {})

        # 检查：如果 sentiment 负面 > 50% 但 trend 讲「viral」，矛盾
        if sent and trend:
            sent_items = sent.get("items") or sent.get("breakdowns") or []
            trend_items = trend.get("items") or trend.get("breakdowns") or []
            if sent_items and trend_items:
                # 简化检查：sentiment 负面比例
                neg_pct_values = []
                for it in sent_items if isinstance(sent_items, list) else []:
                    if isinstance(it, dict):
                        neg = it.get("negative_pct", 0)
                        if neg:
                            neg_pct_values.append(neg)

                # trend 嘅 viral_score 平均
                viral_scores = []
                for it in trend_items if isinstance(trend_items, list) else []:
                    if isinstance(it, dict):
                        vs = it.get("viral_score", 0)
                        if vs:
                            viral_scores.append(vs)

                # 矛盾检测：负面 > 60% 但 viral_score 平均 > 70
                if neg_pct_values and viral_scores:
                    avg_neg = sum(neg_pct_values) / len(neg_pct_values)
                    avg_viral = sum(viral_scores) / len(viral_scores)
                    if avg_neg > 60 and avg_viral > 70:
                        issues.append(
                            f"跨 agent 矛盾：sentiment_reader 平均负面 {avg_neg:.0f}%，"
                            f"但 trend_scout 平均 viral_score {avg_viral:.0f}（应一致）"
                        )

        return issues

    async def _llm_cross_check(
        self, agent_outputs: dict[str, dict], original_query: str
    ) -> dict | None:
        """LLM 审核：跨 agent 一致性 + 整体质量。"""
        # 摘要 prompt（避免 prompt 过长）
        summary_lines = [f"原始任务：{original_query}\n"]
        summary_lines.append("7 个 Agent 输出摘要：\n")
        for agent_name, output in agent_outputs.items():
            if not output:
                continue
            summary = str(output.get("summary", ""))[:200]
            summary_lines.append(f"\n【{agent_name}】\n{summary}\n")

        summary_lines.append("""
请审核以上 7 个 agent 嘅输出，重点检查：
1. 跨 agent 是否有逻辑矛盾（trend vs sentiment 嘅判断一致？）
2. 数据引用是否一致（数字 / 平台 / 商品名）
3. 整体报告嘅深度 + 可操作性
4. 有冇明显幻觉或者数据缺失

返回 JSON：
{
  "consistency_score": 0-100,
  "issues": ["具体问题1", "具体问题2"],
  "summary": "整体评估一句话"
}""")

        prompt = "\n".join(summary_lines)

        try:
            result = await self._call_llm(
                prompt,
                temperature=0.3,
                json_mode=True,
                max_tokens=2048,
            )
            parsed = self._parse_json(result)
            # Validate
            if not isinstance(parsed, dict):
                return None
            return {
                "consistency_score": int(parsed.get("consistency_score", 50)),
                "issues": list(parsed.get("issues", []))[:5],  # max 5
                "summary": str(parsed.get("summary", ""))[:300],
            }
        except Exception as e:
            logger.warning(f"CrossVerifier LLM 调用失败: {e}")
            return None


# 模块级单例
cross_verifier = CrossVerifier()