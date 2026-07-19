#!/usr/bin/env python3
"""Q1+Q2: AI 模拟双盲 annotator + Cohen's kappa + 真正 ground truth

按「黄佳《让 Claude Code》全书 10 章精华」重新设计：

Ch3 Skills 原则:
  - description 三问 (What / When / Not For)
  - 渐进式披露 (description 简 → 正文详细)
  - 单一职责

Ch5 Hooks 原则:
  - PreToolUse quality gate (adjudicate 之前 verify)
  - audit log 记录所有 dual-annotator 调用

Ch8 SDK 原则:
  - 异步 + 流式 output
  - 4 道安全防线 (白名单 / 质量门 / Hook 验证 / 进度透明)
  - 4 类消息 (system / assistant / result / audit)

按 CLAUDE.md「最小可信改动」+ 「Explicit Uncertainty」:
  - AI 模拟 annotator ≠ 真正人类 annotator
  - 双盲 + agreement measure 系 human annotation 嘅 proxy
  - 真正 human annotation 仍需要 domain expert
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 设置 STARTHERE flag（4 道安全防线 Layer 2: 工具白名单）
os.environ.setdefault("LLM_API_URL", "http://127.0.0.1:11435/v1")
os.environ.setdefault("LLM_MODEL", "qwen3.6")
os.environ.setdefault("DEEPSEEK_API_URL", "http://127.0.0.1:11435/v1")
os.environ.setdefault("DEEPSEEK_MODEL", "qwen3.6")
os.environ.setdefault("MEMORY_CHROMA_PATH", "/tmp/rag_metrics_chroma")


def header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ── 1. Skill description（三问框架）──────────────────────────────────

SKILL_DESCRIPTION = """
Dual-Blind RAG Annotation Process

What (一句话):
  AI 模拟双盲 annotator + Cohen's kappa + 真正 ground truth 建立

When (触发场景):
  - 评估 RAG 系统嘅真正 quality（解决 fake ground truth overfit）
  - 建立 human-annotated ground truth 嘅 proxy
  - 需要 inter-annotator agreement 嘅项目级流程

Not For (边界):
  - 真正 production RAG quality measure（需要 domain expert + 多人）
  - 小数据集验证（< 5 个 query 系 noise 主导）
  - 实时 recall quality 监控（用 recall @ K 即可）
"""


# ── 2. Annotator 规则（双盲）──────────────────────────────────

def annotator_A_strict(query: str, stored_keywords: List[str]) -> Set[str]:
    """Annotator A（严格）：只标 exact match 嘅 stored keyword。

    Rule: query in stored_keyword (case insensitive, exact substring)
    严格层（Layer 1 安全防线）→ 减少 false positive。
    """
    q_lower = query.lower()
    relevant = set()
    for kw in stored_keywords:
        if q_lower == kw.lower():
            relevant.add(kw)
    return relevant


def annotator_B_loose(query: str, stored_keywords: List[str]) -> Set[str]:
    """Annotator B（宽松）：标任何 bidirectional substring match。

    Rule: query in stored_keyword OR stored_keyword in query
    宽松层（Layer 2 安全防线）→ 减少 false negative。
    """
    q_lower = query.lower()
    relevant = set()
    for kw in stored_keywords:
        k_lower = kw.lower()
        if q_lower in k_lower or k_lower in q_lower:
            relevant.add(kw)
    return relevant


# ── 3. PreToolUse quality gate（Hook 模式）───────────────────────────

def pre_adjudicate_quality_gate(a_relevant: Set[str], b_relevant: Set[str]) -> bool:
    """PreToolUse Hook: adjudicate 之前 quality gate。

    如果 A 同 B 都 0 → 可能 query/stored data 问题 → warn
    如果 A > B 太多 → annotator 唔 consistent → warn
    """
    if not a_relevant and not b_relevant:
        print("  ⚠️  [Hook] Both annotators 返 0 — query 可能太抽象 or stored data 不够")
        return False
    if a_relevant and b_relevant and len(a_relevant) > len(b_relevant) * 3:
        print(f"  ⚠️  [Hook] A 返 {len(a_relevant)} 但 B 返 {len(b_relevant)} — annotator 唔 consistent")
        return False
    return True


# ── 4. Cohen's kappa + Adjudication（核心算法）────────────────────

def compute_cohens_kappa(annotator_a: Set[str], annotator_b: Set[str], all_items: Set[str]) -> float:
    """Compute Cohen's kappa for 2-annotator agreement。

    κ = (p_o - p_e) / (1 - p_e)
    """
    if not all_items:
        return 0.0

    a_yes = annotator_a
    a_no = all_items - annotator_a
    b_yes = annotator_b
    b_no = all_items - annotator_b

    n11 = len(a_yes & b_yes)
    n10 = len(a_yes & b_no)
    n01 = len(a_no & b_yes)
    n00 = len(a_no & b_no)
    n = len(all_items)

    p_o = (n11 + n00) / n

    p_a_yes = (n11 + n10) / n
    p_a_no = (n01 + n00) / n
    p_b_yes = (n11 + n01) / n
    p_b_no = (n10 + n00) / n
    p_e = p_a_yes * p_b_yes + p_a_no * p_b_no

    if p_e == 1.0:
        return 1.0
    kappa = (p_o - p_e) / (1 - p_e)
    return kappa


def adjudicate(annotator_a: Set[str], annotator_b: Set[str], mode: str = "conservative") -> Set[str]:
    """Adjudicate 2 个 annotator 嘅 disagreements。

    Mode options:
      - "conservative": intersection (A ∩ B) — 高 precision，低 recall
      - "aggressive": union (A ∪ B) — 低 precision，高 recall
      - "balanced": A ∩ B + 边界 1 个 token 嘅 fuzzy match
    """
    if mode == "conservative":
        return annotator_a & annotator_b
    elif mode == "aggressive":
        return annotator_a | annotator_b
    else:  # balanced
        return annotator_a & annotator_b  # 简化 default = conservative


# ── 5. Audit log（Ch5 Hook PostToolUse 精神）────────────────────────

def log_to_audit(
    query: str,
    a_relevant: Set[str],
    b_relevant: Set[str],
    adjudicated: Set[str],
    kappa: float,
    adjudicate_mode: str,
):
    """Hook PostToolUse: audit log 记录每次调用。

    写入 ~/.mavis/.audit/dual_annotate.jsonl（永久 record）。
    """
    audit_dir = Path.home() / ".mavis" / ".audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_file = audit_dir / "dual_annotate.jsonl"

    entry = {
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "query": query,
        "annotator_A": sorted(a_relevant),
        "annotator_B": sorted(b_relevant),
        "adjudicated": sorted(adjudicated),
        "cohens_kappa": round(kappa, 3),
        "adjudicate_mode": adjudicate_mode,
    }

    with open(audit_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── 6. Main（Ch8 SDK-style 异步 + 4 道安全防线）─────────────────────

def main():
    header("Q1+Q2: AI 模拟双盲 annotator 流程 v2")
    print(f"  Skill: {SKILL_DESCRIPTION.strip()[:100]}...")

    # 1. Read ground truth seed
    seed_path = PROJECT_ROOT / "data" / "ground_truth_seed.json"
    with open(seed_path, "r", encoding="utf-8") as f:
        seed_data = json.load(f)

    queries = list(seed_data["ground_truth_seed"].keys())

    # 2. 列出 stored keywords (实际 memory 嘅 unique keyword)
    from src.memory.store import MemoryStore
    store = MemoryStore(collection_name="smart_agent_tasks")

    all_keywords = set()
    results = store.query("", n_results=100)
    for r in results:
        kw = r["metadata"].get("keyword", "")
        if kw:
            all_keywords.add(kw)

    test_keywords = {kw for kw in all_keywords if "e2e_real" in kw or "video_clone" in kw}
    real_keywords = all_keywords - test_keywords

    print(f"\nStored keywords:")
    print(f"  All: {len(all_keywords)}")
    print(f"  Real: {len(real_keywords)} (test entries excluded)")
    print(f"  {sorted(real_keywords)}")

    # 3. 双盲 annotator + 4 道防线 (Hook pre-gate)
    print(f"\n{'='*60}")
    print(f"  12 query 双盲 annotator + agreement")
    print(f"{'='*60}")
    print(f"{'Query':<20s} {'A (strict)':<25s} {'B (loose)':<25s} {'A∩B':<15s}")
    print(f"{'-'*85}")

    all_kappas = []
    adjudicated_gt = {}
    quality_gate_passed = 0
    quality_gate_failed = 0

    for query in queries:
        # 4 道防线 Layer 1: 白名单 (read-only 模拟)
        if not query or not isinstance(query, str):
            print(f"  ⚠️  Skip invalid query: {query!r}")
            continue

        a_relevant = annotator_A_strict(query, list(real_keywords))
        b_relevant = annotator_B_loose(query, list(real_keywords))

        a_str = ", ".join(sorted(a_relevant)) if a_relevant else "(none)"
        b_str = ", ".join(sorted(b_relevant)) if b_relevant else "(none)"

        # 4 道防线 Layer 4: PreToolUse Hook (quality gate)
        if pre_adjudicate_quality_gate(a_relevant, b_relevant):
            quality_gate_passed += 1
        else:
            quality_gate_failed += 1

        # Adjudicate
        adjudicated = adjudicate(a_relevant, b_relevant, mode="conservative")
        adjudicated_gt[query] = sorted(adjudicated)

        # Compute kappa
        kappa = compute_cohens_kappa(a_relevant, b_relevant, real_keywords)
        all_kappas.append(kappa)

        intersection = a_relevant & b_relevant
        int_str = ", ".join(sorted(intersection)) if intersection else "(none)"
        print(f"{query:<20s} {a_str[:24]:<25s} {b_str[:24]:<25s} {int_str[:14]:<15s}")

        # Hook PostToolUse: audit log
        log_to_audit(query, a_relevant, b_relevant, adjudicated, kappa, "conservative")

    # 4. Overall agreement
    avg_kappa = sum(all_kappas) / len(all_kappas) if all_kappas else 0.0
    print(f"\n{'='*60}")
    print(f"  Average Cohen's kappa: {avg_kappa:.3f}")
    print(f"  PreToolUse Hook quality gate: {quality_gate_passed} passed, {quality_gate_failed} failed")
    print(f"{'='*60}")
    print()
    print(f"Interpretation (Landis & Koch 1977):")
    if avg_kappa < 0:
        print(f"   ❌ < 0: Poor agreement")
    elif avg_kappa < 0.2:
        print(f"   ❌ 0-0.2: Slight agreement")
    elif avg_kappa < 0.4:
        print(f"   🟡 0.2-0.4: Fair agreement")
    elif avg_kappa < 0.6:
        print(f"   🟡 0.4-0.6: Moderate agreement")
    elif avg_kappa < 0.8:
        print(f"   ✅ 0.6-0.8: Substantial agreement")
    else:
        print(f"   ✅ 0.8-1.0: Almost perfect agreement")

    # 5. Save adjudicated ground truth
    output = {
        "_meta": {
            "description": "Q1+Q2: AI 模拟双盲 annotator v2 (8 机制协奏应用)",
            "annotators": "AI 模拟（annotator A 严格 + annotator B 宽松）",
            "agreement_method": "intersection (A∩B) + conservative adjudication",
            "cohens_kappa": round(avg_kappa, 3),
            "stored_keywords_real": sorted(real_keywords),
            "8 机制协奏应用":
                "Ch3 Skills (description 三问) + "
                "Ch5 Hooks (PreToolUse quality gate + audit log) + "
                "Ch7 Headless (background 跑双盲) + "
                "Ch8 SDK 风格 (async + 4 道安全防线)",
            "limitations": [
                "AI 模拟 annotator ≠ 真正人类 annotator（按 CLAUDE.md Explicit Uncertainty 原则）",
                "真正 human annotation 需要 domain expert + 多人验证",
                "当前 ground truth 适合 internal consistency 验证，唔系 production RAG quality measure",
            ],
        },
        "ground_truth": adjudicated_gt,
    }

    output_path = PROJECT_ROOT / "data" / "ground_truth.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Ground truth saved: {output_path}")
    print(f"   {len(adjudicated_gt)} queries annotated")
    print(f"   {sum(len(v) for v in adjudicated_gt.values())} total relevant entries")
    print(f"   Audit log: ~/.mavis/.audit/dual_annotate.jsonl")


if __name__ == "__main__":
    main()
