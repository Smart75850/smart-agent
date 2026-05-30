"""Regression Test Runner — 加载 ground truth 数据，运行 agent，评分对比。

Usage:
    python -m eval.runner              # 跑全部 agent 回归测试
    python -m eval.runner TrendScout   # 只跑单个 agent
    python -m eval.runner --report     # 生成 HTML 报告
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eval.metrics import score_output, ScoreResult, WEIGHTS
from eval.judge import LLMJudge, JudgeResult

GROUND_TRUTH_DIR = Path(__file__).parent / "ground_truth"

# agent 名称 → 模块路径映射
AGENT_MAP = {
    "trend_scout": ("TrendScout", "src.orchestrator.agents.trend_scout"),
    "video_analyst": ("VideoAnalyst", "src.orchestrator.agents.video_analyst"),
    "product_miner": ("ProductMiner", "src.orchestrator.agents.product_miner"),
    "copy_writer": ("CopyWriter", "src.orchestrator.agents.copy_writer"),
    "sentiment_reader": ("SentimentReader", "src.orchestrator.agents.sentiment_reader"),
    "content_remixer": ("ContentRemixer", "src.orchestrator.agents.content_remixer"),
    "pic_tactic": ("PicTactic", "src.orchestrator.agents.pic_tactic"),
}


@dataclass
class RunResult:
    agent: str
    case_id: str = ""
    duration_ms: float = 0.0
    auto_score: ScoreResult | None = None
    judge_score: JudgeResult | None = None
    passed: bool = False
    error: str = ""


@dataclass
class SuiteReport:
    agent: str
    total_cases: int = 0
    passed: int = 0
    avg_auto_score: float = 0.0
    avg_judge_score: float = 0.0
    results: list[RunResult] = field(default_factory=list)


async def run_agent(agent_key: str, use_judge: bool = True) -> SuiteReport:
    """对单个 agent 跑全部 ground truth 用例。

    Args:
        agent_key: AGENT_MAP 中的 key（如 "trend_scout"）
        use_judge: 是否启用 LLM-as-Judge（需要 API key）

    Returns:
        SuiteReport
    """
    if agent_key not in AGENT_MAP:
        return SuiteReport(agent=agent_key)

    agent_name, module_path = AGENT_MAP[agent_key]
    gt_file = GROUND_TRUTH_DIR / f"{agent_key}.json"

    if not gt_file.exists():
        return SuiteReport(agent=agent_key, results=[])

    with open(gt_file, "r", encoding="utf-8") as f:
        cases = json.load(f)

    report = SuiteReport(agent=agent_name, total_cases=len(cases))

    # 动态加载 agent 类
    import importlib
    module = importlib.import_module(module_path)
    agent_cls = getattr(module, agent_name)
    agent = agent_cls()

    judge = LLMJudge() if use_judge and agent._api_key else None

    for case in cases:
        case_id = case.get("id", "")
        run_result = RunResult(agent=agent_name, case_id=case_id)

        try:
            t0 = time.perf_counter()

            # 执行 agent
            if agent_key == "trend_scout":
                items = case.get("input", {}).get("items", [])
                platform = case.get("input", {}).get("platform", "bilibili")
                keyword = case.get("input", {}).get("keyword", "")
                output = await agent.run(items=items, platform=platform, keyword=keyword)
                output_dict = {
                    "summary": output.summary,
                    "items": [{"viral_score": it.viral_score, "trend_reason": it.trend_reason,
                               "category": it.category} for it in output.items],
                }
            elif agent_key == "video_analyst":
                items = case.get("input", {}).get("items", [])
                platform = case.get("input", {}).get("platform", "")
                output = await agent.run(items=items, platform=platform)
                output_dict = {
                    "summary": output.summary,
                    "breakdowns": [{"hook_type": b.hook_type, "hook_effectiveness": b.hook_effectiveness,
                                    "pacing": b.pacing, "structure_template": b.structure_template,
                                    "conversion_point": b.conversion_point, "viral_mechanism": b.viral_mechanism,
                                    "learnings": b.learnings} for b in output.items],
                }
            elif agent_key == "product_miner":
                items = case.get("input", {}).get("items", [])
                keyword = case.get("input", {}).get("keyword", "")
                output = await agent.run(items=items, keyword=keyword)
                output_dict = {
                    "summary": output.summary,
                    "products": [{"name": p.name, "category": p.category,
                                  "monetization_potential": p.monetization_potential,
                                  "competitive_advantage": p.competitive_advantage} for p in output.items],
                }
            elif agent_key == "copy_writer":
                keyword = case.get("input", {}).get("keyword", "")
                trend_items = case.get("input", {}).get("trend_items", [])
                products = case.get("input", {}).get("products", [])
                video_breakdowns = case.get("input", {}).get("video_breakdowns", [])
                output = await agent.run(keyword=keyword, trend_items=trend_items,
                                         products=products, video_breakdowns=video_breakdowns)
                output_dict = {
                    "summary": output.summary,
                    "variants": [{"variant": v.variant, "text": v.text, "tone": v.tone,
                                  "target_platform": v.target_platform, "hook": v.hook,
                                  "cta": v.cta, "why_it_works": v.why_it_works} for v in output.variants],
                }
            elif agent_key == "sentiment_reader":
                items = case.get("input", {}).get("items", [])
                platform = case.get("input", {}).get("platform", "")
                output = await agent.run(items=items, platform=platform, fetch_comments=False)
                output_dict = {
                    "overall_sentiment": output.overall_sentiment,
                    "summary": output.summary,
                    "items": [{"sentiment": s.sentiment, "positive_pct": s.positive_pct,
                               "neutral_pct": s.neutral_pct, "negative_pct": s.negative_pct,
                               "key_insights": s.key_insights, "confidence": s.confidence,
                               "monetization_signals": s.monetization_signals} for s in output.items],
                }
            elif agent_key == "content_remixer":
                from src.orchestrator.agents.content_remixer import RemixInput
                inp = RemixInput(
                    mode=case.get("input", {}).get("mode", "summarize"),
                    topic=case.get("input", {}).get("topic", ""),
                    raw_items=case.get("input", {}).get("raw_items", []),
                )
                output = await agent.run(inp)
                output_dict = {
                    "summary": output.summary,
                    "key_keywords": output.key_keywords,
                    "platform_breakdown": output.platform_breakdown,
                }
            elif agent_key == "pic_tactic":
                mode = case.get("input", {}).get("mode", "social")
                topic = case.get("input", {}).get("topic", "")
                platform = case.get("input", {}).get("platform", "")
                output = await agent.run(mode=mode, topic=topic, platform=platform)
                output_dict = {
                    "summary": output.summary,
                    "tactics": [{"scene": t.scene, "target_platform": t.target_platform,
                                 "style": t.style, "color_palette": t.color_palette,
                                 "composition": t.composition, "prompt": t.prompt,
                                 "rationale": t.rationale} for t in output.tactics],
                }
            else:
                run_result.error = f"unsupported agent: {agent_key}"
                report.results.append(run_result)
                continue

            t1 = time.perf_counter()
            run_result.duration_ms = (t1 - t0) * 1000

            # 自动化评分
            run_result.auto_score = score_output(agent_name, output_dict)

            # LLM-as-Judge
            if judge:
                gt = case.get("ground_truth", {})
                run_result.judge_score = await judge.judge(agent_name, output_dict, gt)

            # 通过标准：自动化总分 >= 60
            run_result.passed = run_result.auto_score.total >= 60

        except Exception as exc:
            run_result.error = str(exc)

        report.results.append(run_result)

    # 汇总
    report.passed = sum(1 for r in report.results if r.passed)
    auto_scores = [r.auto_score.total for r in report.results if r.auto_score]
    report.avg_auto_score = round(sum(auto_scores) / len(auto_scores), 1) if auto_scores else 0.0
    judge_scores = [r.judge_score.overall for r in report.results if r.judge_score]
    report.avg_judge_score = round(sum(judge_scores) / len(judge_scores), 1) if judge_scores else 0.0

    return report


async def run_all(use_judge: bool = False) -> list[SuiteReport]:
    """跑全部 agent 回归测试。"""
    reports = []
    for key in AGENT_MAP:
        print(f"Running {key}...")
        report = await run_agent(key, use_judge=use_judge)
        reports.append(report)
        status = "PASS" if report.total_cases > 0 and report.passed == report.total_cases else "FAIL"
        print(f"  {status} | {report.passed}/{report.total_cases} | auto={report.avg_auto_score} | judge={report.avg_judge_score}")
    return reports


# ── CLI ───────────────────────────────────────────────────────

if __name__ == "__main__":
    async def main():
        use_judge = "--judge" in sys.argv
        target = None
        for arg in sys.argv[1:]:
            if not arg.startswith("--") and arg != "judge":
                # 找到 agent key（snake_case → AGENT_MAP key）
                for key in AGENT_MAP:
                    if key.replace("_", "") == arg.lower().replace(" ", ""):
                        target = key
                        break

        if target:
            print(f"Running {target}...")
            report = await run_agent(target, use_judge=use_judge)
            for r in report.results:
                flag = "OK" if r.passed else "FAIL"
                print(f"  [{flag}] {r.case_id} | auto={r.auto_score.total if r.auto_score else 'N/A'} | {r.duration_ms:.0f}ms")
                if r.error:
                    print(f"    ERROR: {r.error}")
            print(f"\nTotal: {report.passed}/{report.total_cases} passed | avg_auto={report.avg_auto_score} | avg_judge={report.avg_judge_score}")
        else:
            reports = await run_all(use_judge=use_judge)
            print("\n" + "=" * 60)
            print("SUMMARY")
            print("=" * 60)
            for r in reports:
                flag = "OK" if r.total_cases > 0 and r.passed == r.total_cases else "FAIL"
                print(f"  [{flag}] {r.agent}: {r.passed}/{r.total_cases} | auto={r.avg_auto_score} | judge={r.avg_judge_score}")

    asyncio.run(main())
