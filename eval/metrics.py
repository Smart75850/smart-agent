"""自动化评分 — 5 维度（Factuality / Completeness / Specificity / Consistency / Actionability）。

可在无 LLM 的情况下做粗筛（检查字段非空、数值范围、关键词密度等），
配合 judge.py 的 LLM-as-Judge 做深度评分。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── 评分维度权重 ──────────────────────────────────────────────

WEIGHTS = {
    "factuality": 0.30,
    "completeness": 0.20,
    "specificity": 0.20,
    "consistency": 0.15,
    "actionability": 0.15,
}


@dataclass
class ScoreResult:
    agent: str
    total: float = 0.0               # 0-100 加权总分
    factuality: float = 0.0
    completeness: float = 0.0
    specificity: float = 0.0
    consistency: float = 0.0
    actionability: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


# ── 基础评分函数 ──────────────────────────────────────────────

def _score_not_empty(value: str | list | dict | None, min_len: int = 1) -> float:
    """字段非空检查。"""
    if value is None:
        return 0.0
    if isinstance(value, str):
        return 1.0 if len(value.strip()) >= min_len else 0.3
    if isinstance(value, (list, dict)):
        return 1.0 if len(value) > 0 else 0.0
    return 1.0


def _score_in_range(value: int | float, lo: int, hi: int) -> float:
    """数值范围检查（0-100 区间为正常，超出扣分）。"""
    if lo <= value <= hi:
        return 1.0
    return max(0.0, 1.0 - abs(value - ((lo + hi) / 2)) / ((hi - lo) / 2) * 0.5)


def _score_has_specifics(text: str) -> float:
    """检查文本是否包含具体数据（百分比、数字、引用）。"""
    if not text:
        return 0.0
    score = 0.0
    if re.search(r'\d+%', text):
        score += 0.3
    if re.search(r'\d+[万亿千百]', text):
        score += 0.3
    if re.search(r'[「「].+[」」]', text):  # 引用
        score += 0.2
    if len(text) >= 30:
        score += 0.2
    return min(1.0, score)


def _score_no_placeholder(text: str) -> float:
    """检查是否包含占位符/模糊表述。"""
    if not text:
        return 0.0
    placeholders = ["需 LLM", "降級", "未知", "通用", "TODO", "待分析", "模板"]
    count = sum(1 for p in placeholders if p in text)
    if count == 0:
        return 1.0
    return max(0.0, 1.0 - count * 0.25)


# ── Per-Agent 评分 ────────────────────────────────────────────

def score_trend_scout(output: dict) -> ScoreResult:
    """TrendScout 输出评分。"""
    items = output.get("items", [])
    result = ScoreResult(agent="TrendScout")

    if not items:
        return result

    # Factuality: viral_score 在 0-100 范围
    scores_f = [_score_in_range(it.get("viral_score", 50), 0, 100) for it in items]
    result.factuality = sum(scores_f) / len(scores_f) * 100 if scores_f else 0

    # Completeness: 必需字段非空
    comp_scores = []
    for it in items:
        field_scores = [
            _score_not_empty(it.get("trend_reason", ""), 20),
            _score_not_empty(it.get("category", "")),
        ]
        comp_scores.append(sum(field_scores) / len(field_scores))
    result.completeness = sum(comp_scores) / len(comp_scores) * 100 if comp_scores else 0

    # Specificity: trend_reason 含具体数据
    spec_scores = [_score_has_specifics(it.get("trend_reason", "")) for it in items]
    result.specificity = sum(spec_scores) / len(spec_scores) * 100 if spec_scores else 0

    # Actionability: 无占位符
    act_scores = [_score_no_placeholder(it.get("trend_reason", "")) for it in items]
    result.actionability = sum(act_scores) / len(act_scores) * 100 if act_scores else 0

    # Consistency: category 不全是 "其他"
    others = sum(1 for it in items if it.get("category") == "其他")
    result.consistency = max(0, 100 - (others / max(len(items), 1)) * 100)

    result.total = _weighted_total(result)
    return result


def score_video_analyst(output: dict) -> ScoreResult:
    """VideoAnalyst 输出评分。"""
    items = output.get("breakdowns", [])
    result = ScoreResult(agent="VideoAnalyst")

    if not items:
        return result

    scores_f = [_score_in_range(it.get("hook_effectiveness", 50), 0, 100) for it in items]
    result.factuality = sum(scores_f) / len(scores_f) * 100 if scores_f else 0

    comp_scores = []
    for it in items:
        field_scores = [
            _score_not_empty(it.get("hook_type", "")),
            _score_not_empty(it.get("pacing", ""), 15),
            _score_not_empty(it.get("structure_template", "")),
            _score_not_empty(it.get("viral_mechanism", ""), 20),
            _score_not_empty(it.get("learnings", ""), 15),
            _score_not_empty(it.get("confidence", "")),
        ]
        comp_scores.append(sum(field_scores) / len(field_scores))
    result.completeness = sum(comp_scores) / len(comp_scores) * 100 if comp_scores else 0

    spec_scores = [_score_has_specifics(it.get("pacing", "") + it.get("learnings", "")) for it in items]
    result.specificity = sum(spec_scores) / len(spec_scores) * 100 if spec_scores else 0

    unknowns = sum(1 for it in items if it.get("hook_type") == "無法判斷")
    result.consistency = max(0, 100 - (unknowns / max(len(items), 1)) * 100)

    act_scores = [_score_no_placeholder(it.get("learnings", "")) for it in items]
    result.actionability = sum(act_scores) / len(act_scores) * 100 if act_scores else 0

    result.total = _weighted_total(result)
    return result


def score_product_miner(output: dict) -> ScoreResult:
    """ProductMiner 输出评分。"""
    items = output.get("products", [])
    result = ScoreResult(agent="ProductMiner")

    if not items:
        return result

    scores_f = [_score_in_range(it.get("monetization_potential", 50), 0, 100) for it in items]
    result.factuality = sum(scores_f) / len(scores_f) * 100 if scores_f else 0

    comp_scores = []
    for it in items:
        field_scores = [
            _score_not_empty(it.get("name", "")),
            _score_not_empty(it.get("competitive_advantage", ""), 15),
            _score_not_empty(it.get("signal_type", "")),
        ]
        comp_scores.append(sum(field_scores) / len(field_scores))
    result.completeness = sum(comp_scores) / len(comp_scores) * 100 if comp_scores else 0

    spec_scores = [_score_has_specifics(it.get("competitive_advantage", "")) for it in items]
    result.specificity = sum(spec_scores) / len(spec_scores) * 100 if spec_scores else 0

    no_signal = sum(1 for it in items if it.get("signal_type") == "no_signal")
    result.consistency = 100 if no_signal == 0 else max(0, 100 - (no_signal / max(len(items), 1)) * 50)

    act_scores = [_score_no_placeholder(it.get("competitive_advantage", "")) for it in items]
    result.actionability = sum(act_scores) / len(act_scores) * 100 if act_scores else 0

    result.total = _weighted_total(result)
    return result


def score_copy_writer(output: dict) -> ScoreResult:
    """CopyWriter 输出评分。"""
    items = output.get("variants", [])
    result = ScoreResult(agent="CopyWriter")

    if not items:
        return result

    comp_scores = []
    for it in items:
        field_scores = [
            _score_not_empty(it.get("text", ""), 20),
            _score_not_empty(it.get("hook", ""), 10),
            _score_not_empty(it.get("cta", "")),
            _score_not_empty(it.get("why_it_works", ""), 15),
        ]
        comp_scores.append(sum(field_scores) / len(field_scores))
    result.completeness = sum(comp_scores) / len(comp_scores) * 100 if comp_scores else 0

    spec_scores = [_score_has_specifics(it.get("why_it_works", "")) for it in items]
    result.specificity = sum(spec_scores) / len(spec_scores) * 100 if spec_scores else 0

    platforms = set(it.get("target_platform", "") for it in items)
    result.consistency = min(100, len(platforms) * 25)

    act_scores = [_score_no_placeholder(it.get("text", "")) for it in items]
    result.actionability = sum(act_scores) / len(act_scores) * 100 if act_scores else 0

    # 文案类 factuality: 检查 keyword 是否在文案中出现
    kw_match = sum(1 for it in items if it.get("text", ""))
    result.factuality = 85.0 if len(items) >= 2 else 50.0  # 至少2个变体
    result.total = _weighted_total(result)
    return result


def score_sentiment_reader(output: dict) -> ScoreResult:
    """SentimentReader 输出评分。"""
    items = output.get("items", [])
    result = ScoreResult(agent="SentimentReader")

    if not items:
        return result

    for it in items:
        pct_sum = it.get("positive_pct", 0) + it.get("neutral_pct", 0) + it.get("negative_pct", 0)
        if pct_sum == 0 or abs(pct_sum - 100) <= 3:
            result.factuality += 1.0
    result.factuality = (result.factuality / max(len(items), 1)) * 100

    comp_scores = []
    for it in items:
        field_scores = [
            _score_not_empty(it.get("key_insights", ""), 15),
            _score_not_empty(it.get("confidence", "")),
            _score_not_empty(it.get("monetization_signals", ""), 15),
        ]
        comp_scores.append(sum(field_scores) / len(field_scores))
    result.completeness = sum(comp_scores) / len(comp_scores) * 100 if comp_scores else 0

    spec_scores = [_score_has_specifics(it.get("monetization_signals", "")) for it in items]
    result.specificity = sum(spec_scores) / len(spec_scores) * 100 if spec_scores else 0

    low_conf = sum(1 for it in items if it.get("confidence") == "low")
    result.consistency = 100 if low_conf == 0 else max(50, 100 - low_conf * 15)

    act_scores = [_score_no_placeholder(it.get("key_insights", "")) for it in items]
    result.actionability = sum(act_scores) / len(act_scores) * 100 if act_scores else 0

    result.total = _weighted_total(result)
    return result


def score_content_remixer(output: dict) -> ScoreResult:
    """ContentRemixer 输出评分。"""
    result = ScoreResult(agent="ContentRemixer")

    result.completeness = _score_not_empty(output.get("summary", ""), 20) * 100

    insights = output.get("track_insights", [])
    rewrites = output.get("rewrites", [])

    if insights:
        spec_scores = [_score_has_specifics(
            t.get("entry_barrier", "") + t.get("recommended_angles", "")
        ) for t in insights]
        result.specificity = sum(spec_scores) / len(spec_scores) * 100 if spec_scores else 0

        scores_f = [_score_in_range(t.get("opportunity_score", 50), 0, 100) for t in insights]
        result.factuality = sum(scores_f) / len(scores_f) * 100 if scores_f else 0
    elif rewrites:
        result.specificity = _score_has_specifics(
            " ".join(r.get("changes_summary", "") for r in rewrites)
        ) * 100
        result.factuality = 80.0
    else:
        result.specificity = 50.0
        result.factuality = 70.0

    result.consistency = _score_no_placeholder(output.get("summary", "")) * 100
    result.actionability = _score_no_placeholder(output.get("recommendations", "")) * 100

    result.total = _weighted_total(result)
    return result


def score_pic_tactic(output: dict) -> ScoreResult:
    """PicTactic 输出评分。"""
    items = output.get("tactics", [])
    result = ScoreResult(agent="PicTactic")

    if not items:
        return result

    comp_scores = []
    for it in items:
        field_scores = [
            _score_not_empty(it.get("style", ""), 10),
            _score_not_empty(it.get("color_palette", ""), 10),
            _score_not_empty(it.get("composition", ""), 15),
            _score_not_empty(it.get("prompt", ""), 30),
            _score_not_empty(it.get("rationale", ""), 15),
        ]
        comp_scores.append(sum(field_scores) / len(field_scores))
    result.completeness = sum(comp_scores) / len(comp_scores) * 100 if comp_scores else 0

    # 检查是否违规使用了 HEX 色号
    hex_violations = sum(1 for it in items if re.search(r'#[0-9A-Fa-f]{6}', it.get("color_palette", "")))
    result.factuality = max(0, 100 - hex_violations * 30)

    # prompt 是否为英文 + 足够长
    prompt_scores = []
    for it in items:
        p = it.get("prompt", "")
        is_english = 1.0 if re.match(r'^[a-zA-Z\s,]+', p) else 0.3
        is_long = min(1.0, len(p) / 50)
        prompt_scores.append((is_english + is_long) / 2)
    result.specificity = sum(prompt_scores) / len(prompt_scores) * 100 if prompt_scores else 0

    result.consistency = _score_no_placeholder(output.get("summary", "")) * 100
    result.actionability = sum(
        _score_no_placeholder(it.get("prompt", "")) for it in items
    ) / len(items) * 100 if items else 0

    result.total = _weighted_total(result)
    return result


# ── 通用入口 ──────────────────────────────────────────────────

SCORERS = {
    "TrendScout": score_trend_scout,
    "VideoAnalyst": score_video_analyst,
    "ProductMiner": score_product_miner,
    "CopyWriter": score_copy_writer,
    "SentimentReader": score_sentiment_reader,
    "ContentRemixer": score_content_remixer,
    "PicTactic": score_pic_tactic,
}


def _weighted_total(result: ScoreResult) -> float:
    return round(
        result.factuality * WEIGHTS["factuality"]
        + result.completeness * WEIGHTS["completeness"]
        + result.specificity * WEIGHTS["specificity"]
        + result.consistency * WEIGHTS["consistency"]
        + result.actionability * WEIGHTS["actionability"],
        1,
    )


def score_output(agent: str, output: dict) -> ScoreResult:
    """对单个 agent 的输出做自动化评分。

    Args:
        agent: agent 名称（TrendScout / VideoAnalyst / ...）
        output: agent 输出的 dict

    Returns:
        ScoreResult with 5-dimension scores and weighted total
    """
    scorer = SCORERS.get(agent)
    if scorer is None:
        return ScoreResult(agent=agent, details={"error": f"unknown agent: {agent}"})
    return scorer(output)
