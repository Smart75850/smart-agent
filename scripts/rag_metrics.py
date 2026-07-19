#!/usr/bin/env python3
"""N2: RAG 真实质量 metrics (precision@K, recall@K, MRR)

按 smart-agent CLAUDE.md「Explicit Uncertainty」原则：
- 用 ground truth 验证 recall accuracy
- 跑多 query 计算 metrics
- 输出可重复嘅 RAG quality report

Ground truth（手动定义，基于 M3 验证）：
- "AI Agent" → ["AI Agent 2026", "AI 工具实战"] (top 2 相关)
- "AI 工具" → ["AI 工具实战", "AI Agent 2026"] (top 2 相关)
- "美妆" → ["美妆视频"] (top 1)
- "Python" → ["Python 教程"] (top 1)

Metrics:
- Precision@K = relevant_in_top_K / K
- Recall@K = relevant_in_top_K / total_relevant
- MRR = 1 / rank_of_first_relevant (mean across queries)
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import List, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 设置 STARTHERE flag
os.environ.setdefault("LLM_API_URL", "http://127.0.0.1:11435/v1")
os.environ.setdefault("LLM_MODEL", "qwen3.6")
os.environ.setdefault("DEEPSEEK_API_URL", "http://127.0.0.1:11435/v1")
os.environ.setdefault("DEEPSEEK_MODEL", "qwen3.6")
os.environ.setdefault("MEMORY_SAVE_ENABLED", "true")
os.environ.setdefault("RECALL_RERANK_ENABLED", "true")
os.environ.setdefault("MEMORY_CHROMA_PATH", "/tmp/rag_metrics_chroma")


# Ground truth：query → expected relevant keywords
GROUND_TRUTH: Dict[str, List[str]] = {
    "AI Agent": ["AI Agent 2026", "AI 工具实战"],
    "AI 工具": ["AI 工具实战", "AI Agent 2026"],
    "美妆": ["美妆视频"],
    "Python": ["Python 教程"],
    "AI Agent 工具": ["AI Agent 2026", "AI 工具实战"],  # cross-keyword
    "Python 编程": ["Python 教程"],  # single keyword
}


def header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


async def run_pipelines_and_save():
    """跑 4 个真实 pipeline（写入 memory）。"""
    from src.orchestrator.pipeline import run_pipeline

    keywords = [
        ("AI Agent 2026", "bilibili"),
        ("AI 工具实战", "bilibili"),
        ("美妆视频", "bilibili"),
        ("Python 教程", "bilibili"),
    ]

    # 跳过已存在嘅 entry（incremental test）
    from src.memory.store import MemoryStore
    store = MemoryStore(collection_name="smart_agent_tasks")
    existing_keywords = set()
    if store.count() > 0:
        # 抽 existing keywords from store
        results = store.query("Agent OR 工具 OR 美妆 OR Python", n_results=100)
        for r in results:
            kw = r["metadata"].get("keyword", "")
            if kw:
                existing_keywords.add(kw)

    # N2 fix：唔好 unpack string 第一个 char，保留 (kw, platform) tuple
    new_runs = [(kw, platform) for kw, platform in keywords if kw not in existing_keywords]

    if not new_runs:
        print(f"✅ All 4 keywords already in memory ({store.count()} entries)")
        return 0

    print(f"跑 {len(new_runs)} new pipeline runs...")
    for kw, platform in new_runs:
        print(f"  → {kw}")
        try:
            result = await run_pipeline(
                keyword=kw,
                limit=5,
                platforms=[platform],
                pipeline_mode="full",
                llm_filter=False,
            )
            print(f"    ✅ {len(result.get('final_output', []))} 条")
        except Exception as e:
            print(f"    ❌ Error: {e}")
    return len(new_runs)


def precision_at_k(retrieved: List[Dict], expected: List[str], k: int) -> float:
    """Precision@K = relevant_in_top_K / K"""
    if k == 0:
        return 0.0
    top_k_kws = [r["metadata"].get("keyword", "") for r in retrieved[:k]]
    relevant = sum(1 for kw in top_k_kws if kw in expected)
    return relevant / k


def recall_at_k(retrieved: List[Dict], expected: List[str], k: int) -> float:
    """Recall@K = relevant_in_top_K / total_relevant"""
    if not expected:
        return 0.0
    top_k_kws = [r["metadata"].get("keyword", "") for r in retrieved[:k]]
    relevant = sum(1 for kw in top_k_kws if kw in expected)
    return min(relevant / len(expected), 1.0)


def mrr(retrieved: List[Dict], expected: List[str]) -> float:
    """MRR = 1 / rank_of_first_relevant (0 if not found)"""
    for i, r in enumerate(retrieved, 1):
        if r["metadata"].get("keyword", "") in expected:
            return 1.0 / i
    return 0.0


def evaluate_metrics():
    """计算并输出 RAG quality metrics。"""
    from src.memory.recall import recall_similar_tasks
    from src.memory.store import MemoryStore

    store = MemoryStore(collection_name="smart_agent_tasks")
    print(f"\nMemory 总数: {store.count()} entries")

    p_at_1_list = []
    p_at_3_list = []
    r_at_3_list = []
    mrr_list = []

    print(f"\n{'='*60}")
    print(f"{'Query':<20s} {'P@1':<8s} {'P@3':<8s} {'R@3':<8s} {'MRR':<8s} {'Top-1':<25s}")
    print(f"{'='*60}")

    for query, expected in GROUND_TRUTH.items():
        results = recall_similar_tasks(query, top_k=5, store=store, rerank=True)

        p1 = precision_at_k(results, expected, 1)
        p3 = precision_at_k(results, expected, 3)
        r3 = recall_at_k(results, expected, 3)
        m = mrr(results, expected)

        p_at_1_list.append(p1)
        p_at_3_list.append(p3)
        r_at_3_list.append(r3)
        mrr_list.append(m)

        top1_kw = results[0]["metadata"].get("keyword", "") if results else "N/A"
        top1_score = results[0].get("rerank_score", 0) if results else 0
        top1_str = f"{top1_kw} ({top1_score:.2f})" if results else "N/A"

        print(f"{query:<20s} {p1:<8.2f} {p3:<8.2f} {r3:<8.2f} {m:<8.2f} {top1_str:<25s}")

    # Macro average
    print(f"{'='*60}")
    print(f"{'MACRO AVG':<20s} {sum(p_at_1_list)/len(p_at_1_list):<8.2f} {sum(p_at_3_list)/len(p_at_3_list):<8.2f} {sum(r_at_3_list)/len(r_at_3_list):<8.2f} {sum(mrr_list)/len(mrr_list):<8.2f}")

    # Quality assessment
    macro_p1 = sum(p_at_1_list) / len(p_at_1_list)
    macro_mrr = sum(mrr_list) / len(mrr_list)

    print(f"\n📊 Quality Assessment:")
    if macro_p1 >= 0.8:
        print(f"   ✅ P@1 = {macro_p1:.2f} (>= 0.8: 优秀)")
    elif macro_p1 >= 0.6:
        print(f"   🟡 P@1 = {macro_p1:.2f} (>= 0.6: 良好)")
    else:
        print(f"   ❌ P@1 = {macro_p1:.2f} (< 0.6: 需改进)")

    if macro_mrr >= 0.8:
        print(f"   ✅ MRR = {macro_mrr:.2f} (>= 0.8: 优秀)")
    elif macro_mrr >= 0.6:
        print(f"   🟡 MRR = {macro_mrr:.2f} (>= 0.6: 良好)")
    else:
        print(f"   ❌ MRR = {macro_mrr:.2f} (< 0.6: 需改进)")


async def main():
    header("N2: RAG 质量 Metrics (Precision/Recall/MRR)")

    # 1. 跑 pipeline 写入 memory（如有需要）
    await run_pipelines_and_save()

    # 2. 计算 metrics
    evaluate_metrics()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
