"""Critic Agent — Self-Reflection Pattern (Phase D).

每个 Agent 输出后，Critic 做 quality gate：
  PASS → 直接输出
  FAIL → 退回 Agent 修正（带 feedback），最多重试 2 次

参考：Anthropic Agent Design Pattern #4 + LangGraph Self-Correcting
效果：准确度 +30-50%，成本 x1.3-1.5

用法：
  critic = CriticAgent("trend_scout")
  result = await critic.review(output_dict)
  if not result.passed:
      # 用 result.feedback 重试 Agent
"""

from __future__ import annotations
import re

import json
from dataclasses import dataclass, field
from typing import Any

from src.orchestrator.agents.base import BaseAgent
from src.utils.logger import logger


@dataclass
class CriticResult:
    passed: bool = False
    score: int = 0            # 0-100
    feedback: str = ""        # 修正建议（给 Agent 的 retry prompt）
    issues: list[str] = field(default_factory=list)
    severity: str = "low"     # low / medium / high


# ── 每个 Agent 的质量检查标准 ────────────────────────────────

CRITERIA: dict[str, dict] = {
    "trend_scout": {
        "checks": [
            "viral_score 评分是否有鉴别度（不能全部一样，标准差应 >8）",
            "trend_reason 是否具体（>=20字，含数据引用如播放量/互动比）",
            "category 是否为合法枚举值（15类之一，不能滥用「其他」）",
            "summary 是否总结整体趋势（>=30字，含赛道判断+机会信号）",
        ],
        # N1 fix：threshold 65 → 50（避免 Critic 评分严苛导致 fallback hot-sort）
        "pass_threshold": 50,
        "max_retry": 1,
    },
    "video_analyst": {
        "checks": [
            "hook_type 是否为合法枚举值（9种之一），接受繁简体差异",
            "learnings 是否有可操作建议（>=10字）",
            "confidence 是否合理标注（无数据→low）",
            "pacing 描述是否具体",
        ],
        "pass_threshold": 55,
        "max_retry": 1,
    },
    "product_miner": {
        "checks": [
            "signal_type 是否标注 direct/indirect/no_signal",
            "monetization_potential 评分有鉴别度",
            "输出商品/品牌是否来自输入数据（非幻觉编造）",
        ],
        "pass_threshold": 55,
        "max_retry": 1,
    },
    "sentiment_reader": {
        "checks": [
            "confidence 是否根据评论数量合理标注（<10条→low）",
            "monetization_signals 是否捕捉购买意愿信号",
        ],
        "pass_threshold": 55,
        "max_retry": 1,
    },
    "copy_writer": {
        "checks": [
            "文案是否可直接发布（非半成品/占位符）",
            "hook 设计是否符合平台特征",
            "why_it_works 是否解释传播机制",
        ],
        "pass_threshold": 60,
        "max_retry": 1,
    },
    "content_remixer": {
        "checks": [
            "competition_level 判断是否有数据支撑（非模糊「中」）",
            "entry_barrier 描述是否具体（>=15字，含资金/技术/资源）",
            "recommended_angles 是否具体可执行的角度",
            "recommendations 是否 actionable（非「做内容」「做营销」）",
        ],
        "pass_threshold": 60,
        "max_retry": 2,
    },
    "content_remixer_analyze": {
        "checks": [
            "competition_level 判断是否有数据支撑（非模糊「中」）",
            "entry_barrier 描述是否具体（>=30字，含资金/技术/资源量化）",
            "recommended_angles 是否具体可执行（>=40字，含目标人群+差异化+执行路径）",
            "recommendations 是否 actionable（含优先级+资源需求）",
        ],
        "pass_threshold": 65,
        "max_retry": 1,
    },
    "content_remixer_rewrite": {
        "checks": [
            "改寫是否体现平台差异（非仅加emoji）",
            "changes_summary 是否含语言/节奏/信息密度/情绪四个维度",
            "rewritten 内容长度是否合理（>=30字）",
        ],
        "pass_threshold": 65,
        "max_retry": 1,
    },
    "pic_tactic": {
        "checks": [
            "prompt 是否为英文（Midjourney/SD 兼容）",
            "color_palette 是否用色彩形容词（非 HEX 色号）",
            "composition 描述是否具体（>=20字，含比例+元素布局）",
            "rationale 是否结合平台用户偏好+数据依据",
        ],
        "pass_threshold": 75,
        "max_retry": 1,
    },
}


class CriticAgent(BaseAgent):
    """质量审查 Agent — 用 LLM 检查 Agent 输出质量。

    同时包含规则级 fallback（无 API key 时使用）。
    """

    def __init__(self, agent_type: str):
        super().__init__()
        self.agent_type = agent_type
        self.criteria = CRITERIA.get(agent_type, {})
        if not self.criteria:
            logger.warning(f"CriticAgent: 未知 agent_type={agent_type}，使用默认标准")
            self.criteria = {
                "checks": ["输出是否完整", "字段是否非空", "数据是否合理"],
                "pass_threshold": 60,
                "max_retry": 1,
            }

    async def review(
        self,
        output: dict,
        input_context: str = "",
        previous_feedback: str = "",
    ) -> CriticResult:
        """审查 Agent 输出质量。

        Args:
            output: Agent 输出的 dict
            input_context: 原始输入上下文（用于判断相关性）
            previous_feedback: 上一轮的 feedback（检查是否已修正）

        Returns:
            CriticResult with passed/score/feedback
        """
        # 1. 规则级快速检查（无 API key 时的主要手段）
        rule_result = self._rule_based_check(output)
        if rule_result.passed and not self._api_key:
            return rule_result

        # 2. LLM 深度检查
        if self._api_key:
            try:
                return await self._llm_review(output, input_context, previous_feedback)
            except Exception as exc:
                logger.warning(f"Critic LLM 检查失败，降级为规则检查: {exc}")
                return rule_result

        return rule_result

    def can_retry(self, attempt: int) -> bool:
        max_retry = self.criteria.get("max_retry", 2)
        return attempt < max_retry

    # ── internal ──────────────────────────────────────────────

    async def _llm_review(
        self,
        output: dict,
        input_context: str,
        previous_feedback: str,
    ) -> CriticResult:
        """LLM 深度质量检查。"""
        checks = self.criteria.get("checks", [])
        threshold = self.criteria.get("pass_threshold", 70)

        checks_text = "\n".join(f"{i+1}. {c}" for i, c in enumerate(checks))
        output_text = json.dumps(output, ensure_ascii=False, indent=2)

        fb_section = ""
        if previous_feedback:
            fb_section = f"\n## 上次反馈（请检查是否已修正）\n{previous_feedback}\n"

        input_section = ""
        if input_context:
            input_section = f"\n## 原始输入数据（用于检查输出是否与输入相关、有无幻觉）\n{input_context[:2000]}\n⚠️ 请检查：输出中引用的数据/商品/标题是否能在输入中找到对应项。如有编造，严重扣分。\n"

        prompt = f"""你是严格的质量审查员（Critic），负责检查 {self.agent_type} Agent 的输出质量。

## 检查清单
{checks_text}
6. **输入相关性**：输出内容是否与输入数据相关？有无编造输入中不存在的商品名/数据/标题？

## 通过标准
总分 >= {threshold} 分视为通过。低于此分数需要退回修正。

## 评分规则
- 90-100：优秀，所有检查项通过
- 70-89：良好，有少量小问题但不影响使用
- 50-69：一般，有明显问题需要修正
- <50：差，必须重做
{fb_section}{input_section}
## Agent 输出
```json
{output_text}
```

## 输出格式
返回纯 JSON（不要 markdown 代码块）：
{{"score": 0-100, "passed": true/false,
  "issues": ["问题1", "问题2"],
  "feedback": "具体的修正建议（50字以上，告诉Agent哪里不对、怎么改）",
  "severity": "low/medium/high"}}"""

        content = await self._call_llm(prompt, temperature=0.1, json_mode=True, max_tokens=1000)
        parsed = self._parse_json(content)

        return CriticResult(
            passed=parsed.get("passed", False),
            score=parsed.get("score", 50),
            feedback=parsed.get("feedback", ""),
            issues=parsed.get("issues", []),
            severity=parsed.get("severity", "medium"),
        )

    def _rule_based_check(self, output: dict) -> CriticResult:
        """规则级快速检查（无 LLM 依赖）。"""
        issues = []
        score = 100
        agent = self.agent_type

        # 通用检查：输出非空
        items_key = {
            "trend_scout": "items",
            "video_analyst": "breakdowns",
            "product_miner": "products",
            "sentiment_reader": "items",
            "copy_writer": "variants",
            "content_remixer": "track_insights",
            "pic_tactic": "tactics",
        }.get(agent, "items")

        items = output.get(items_key, [])
        if isinstance(items, list) and len(items) == 0:
            # 空列表不一定错（如 product_miner 无商品信号）
            if agent not in ("product_miner",):
                issues.append(f"{items_key} 为空")
                score -= 30

        # Summary 非空
        summary = output.get("summary", "")
        if not summary or len(str(summary)) < 10:
            issues.append("summary 过短或为空")
            score -= 20

        # 按 agent 特定规则
        if agent == "trend_scout":
            scores = [it.get("viral_score", 50) for it in items if isinstance(it, dict)]
            if len(scores) >= 3:
                import statistics
                try:
                    stdev = statistics.stdev(scores)
                    if stdev < 5:
                        issues.append(f"viral_score 无鉴别度 (std={stdev:.1f})")
                        score -= 15
                except:
                    pass
            # 检查「其他」滥用
            cats = [it.get("category", "") for it in items if isinstance(it, dict)]
            other_count = sum(1 for c in cats if c == "其他")
            if other_count > len(cats) * 0.3 if cats else 0:
                issues.append(f"category「其他」占比过高 ({other_count}/{len(cats)})")
                score -= 10

        elif agent == "copy_writer":
            for idx, v in enumerate(items if isinstance(items, list) else []):
                if not isinstance(v, dict):
                    continue
                why = v.get("why_it_works", "")
                text = v.get("text", "")
                hook = v.get("hook", "")
                if why and not re.search(r'\d+', why):
                    issues.append(f"variant[{idx}] why_it_works 缺数字")
                    score -= 8
                if why and len(why) < 20:
                    issues.append(f"variant[{idx}] why_it_works 过短（{len(why)}字，需>=20）")
                    score -= 8
                if hook and any(g in hook for g in ["钩子", "吸引", "有趣", "好看", "鈎子"]):
                    issues.append(f"variant[{idx}] hook 描述太通用（'{hook[:20]}'），需具体手法")
                    score -= 10
                if text and len(text) > 20 and not re.search(r'\d+', text):
                    issues.append(f"variant[{idx}] 文案缺具体数字或品牌名")
                    score -= 5

        elif agent == "video_analyst":
            unknown_hooks = sum(1 for it in items if isinstance(it, dict) and it.get("hook_type") == "無法判斷")
            if unknown_hooks > len(items) * 0.4:
                issues.append(f"hook_type「無法判斷」过多 ({unknown_hooks}/{len(items)})")
                score -= 20

        elif agent == "sentiment_reader":
            for it in (items or []):
                if isinstance(it, dict):
                    pct_sum = it.get("positive_pct", 0) + it.get("neutral_pct", 0) + it.get("negative_pct", 0)
                    if pct_sum > 0 and abs(pct_sum - 100) > 10:
                        issues.append(f"情绪百分比加总异常: {pct_sum}%")
                        score -= 15
                        break

        elif agent == "pic_tactic":
            for it in (items or []):
                if isinstance(it, dict):
                    cp = it.get("color_palette", "")
                    if re.search(r'#[0-9A-Fa-f]{6}', cp):
                        issues.append("color_palette 包含 HEX 色号（违规）")
                        score -= 20
                        break
                    prompt = it.get("prompt", "")
                    if prompt and not re.match(r'^[a-zA-Z]', prompt):
                        issues.append("AI prompt 不是英文开头")
                        score -= 15
                        break

        passed = score >= self.criteria.get("pass_threshold", 70)
        feedback = "; ".join(issues) if issues else "所有规则检查通过"

        return CriticResult(
            passed=passed,
            score=score,
            feedback=feedback,
            issues=issues,
            severity="high" if score < 50 else ("medium" if score < 70 else "low"),
        )


# ── Feature Flag ─────────────────────────────────────────────

CRITIC_CONFIG = {
    "enabled": True,
    "agents": ["trend_scout", "video_analyst", "product_miner",
               "sentiment_reader", "copy_writer", "content_remixer_analyze",
               "content_remixer_rewrite", "pic_tactic"],
    "max_retry": 1,  # 之前 2 → 3 attempts，每次 30s 太慢。改为 1 → 2 attempts，节省 ~30s per agent
    "critic_model": "deepseek-chat",
}
