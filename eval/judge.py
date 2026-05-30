"""LLM-as-Judge — 用 DeepSeek V4 Pro 做裁判评分。

设计参考 LangChain calibration 方法：
1. 先人工标注 20 条 gold standard
2. 用 gold standard calibrate judge
3. Target: 0.80 Spearman correlation with human judgment

Usage:
    python -m eval.judge --calibrate    # 校准 judge
    python -m eval.judge --score <file> # 对单个输出评分
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eval.metrics import WEIGHTS

GROUND_TRUTH_DIR = Path(__file__).parent / "ground_truth"

JUDGE_SYSTEM_PROMPT = """你是一个严格的内容质量裁判（LLM-as-Judge），负责评估 AI Agent 输出的质量。

## 评分维度

对于给定的 Agent 输出和参考标准（ground truth），在以下 5 个维度打分（每个维度 0-100）：

1. **Factuality (事实准确性)** — 30%
   - 输出中的数据和事实是否有依据
   - 无虚构/幻觉内容
   - 分数范围合理（如 viral_score 在 0-100）

2. **Completeness (完整性)** — 20%
   - 是否覆盖了所有关键分析维度
   - 必需字段是否都已填充
   - 有无遗漏重要信息

3. **Specificity (具体度)** — 20%
   - 描述是否具体可验证
   - 是否包含具体数字、百分比、引用
   - 避免空泛描述如"内容不错""有潜力"

4. **Consistency (一致性)** — 15%
   - 同类输入是否产生一致的分析质量
   - 分类/标签是否合理一致
   - 无逻辑矛盾

5. **Actionability (可操作性)** — 15%
   - 输出是否可直接用于决策
   - 建议是否具体可执行
   - 无模糊/占位符内容

## 输出格式
返回纯 JSON：
{"factuality": 0-100, "completeness": 0-100, "specificity": 0-100,
 "consistency": 0-100, "actionability": 0-100,
 "overall": 0-100,
 "comment": "一句话评语（20字以上，指出现有最佳维度+最需改善维度）"}
"""


@dataclass
class JudgeResult:
    factuality: float = 0.0
    completeness: float = 0.0
    specificity: float = 0.0
    consistency: float = 0.0
    actionability: float = 0.0
    overall: float = 0.0
    comment: str = ""


class LLMJudge:
    """LLM-as-Judge 裁判。"""

    def __init__(self, api_key: str | None = None, api_url: str | None = None, model: str | None = None):
        from config.settings import settings
        self._api_key = api_key or settings.DEEPSEEK_API_KEY or settings.LLM_API_KEY
        self._api_url = api_url or settings.DEEPSEEK_API_URL or settings.LLM_API_URL or "https://api.deepseek.com/v1"
        self._model = model or settings.DEEPSEEK_MODEL or settings.LLM_MODEL or "deepseek-chat"

    async def judge(self, agent: str, output: dict, ground_truth: dict | None = None) -> JudgeResult:
        """评估单个 agent 输出。

        Args:
            agent: agent 名称
            output: agent 输出 dict
            ground_truth: 可选参考标准

        Returns:
            JudgeResult
        """
        import httpx

        output_str = json.dumps(output, ensure_ascii=False, indent=2)
        gt_section = ""
        if ground_truth:
            gt_section = f"\n\n## 参考标准 (Ground Truth)\n```json\n{json.dumps(ground_truth, ensure_ascii=False, indent=2)}\n```"

        prompt = f"""{JUDGE_SYSTEM_PROMPT}

## Agent 类型
{agent}

## Agent 输出
```json
{output_str}
```{gt_section}

请对上述输出在 5 个维度打分，返回 JSON。"""

        body = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 500,
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._api_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            data = resp.json()
            content = data["choices"][0]["message"]["content"]

        from src.orchestrator.agents.base import BaseAgent
        parsed = BaseAgent._parse_json(content)

        return JudgeResult(
            factuality=parsed.get("factuality", 0),
            completeness=parsed.get("completeness", 0),
            specificity=parsed.get("specificity", 0),
            consistency=parsed.get("consistency", 0),
            actionability=parsed.get("actionability", 0),
            overall=parsed.get("overall", 0),
            comment=parsed.get("comment", ""),
        )

    async def calibrate(self) -> dict:
        """用 ground truth 数据校准 judge。

        加载所有 ground truth 文件，逐一评分，
        输出校准报告（需后续与人工评分做 Spearman correlation）。
        """
        results = {}
        for gt_file in sorted(GROUND_TRUTH_DIR.glob("*.json")):
            agent = gt_file.stem.replace("_", " ").title().replace(" ", "")
            with open(gt_file, "r", encoding="utf-8") as f:
                cases = json.load(f)

            agent_results = []
            for case in cases:
                output = case.get("output", {})
                gt = case.get("ground_truth", {})
                result = await self.judge(agent, output, gt)
                agent_results.append({
                    "case_id": case.get("id", ""),
                    "judge_scores": {
                        "factuality": result.factuality,
                        "completeness": result.completeness,
                        "specificity": result.specificity,
                        "consistency": result.consistency,
                        "actionability": result.actionability,
                        "overall": result.overall,
                    },
                    "comment": result.comment,
                })

            results[agent] = agent_results

        return results


# ── CLI ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    async def main():
        judge = LLMJudge()

        if "--calibrate" in sys.argv:
            print("正在校准 LLM Judge...")
            results = await judge.calibrate()
            print(json.dumps(results, ensure_ascii=False, indent=2))
        elif "--score" in sys.argv:
            idx = sys.argv.index("--score")
            filepath = sys.argv[idx + 1]
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            agent = data.get("agent", "Unknown")
            output = data.get("output", {})
            result = await judge.judge(agent, output)
            print(json.dumps({
                "agent": agent,
                "factuality": result.factuality,
                "completeness": result.completeness,
                "specificity": result.specificity,
                "consistency": result.consistency,
                "actionability": result.actionability,
                "overall": result.overall,
                "comment": result.comment,
            }, ensure_ascii=False, indent=2))
        else:
            print("用法: python -m eval.judge --calibrate | --score <file>")

    asyncio.run(main())
