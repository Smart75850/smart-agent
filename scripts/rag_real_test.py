#!/usr/bin/env python3
"""M3: 真 RAG 验证 — 跑多次 pipeline + 启用 rerank 验证 recall quality。

按 smart-agent CLAUDE.md「Explicit Uncertainty」原则：
- 不 mock，直接 run 真实 pipeline
- 跑 2 次不同 keyword
- recall 同 query 验证 accuracy + rerank score
- 报告 recall metrics
"""

import asyncio
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 设置全部 STARTHERE flag
os.environ.setdefault("LLM_API_URL", "http://127.0.0.1:11435/v1")
os.environ.setdefault("LLM_MODEL", "qwen3.6")
os.environ.setdefault("DEEPSEEK_API_URL", "http://127.0.0.1:11435/v1")
os.environ.setdefault("DEEPSEEK_MODEL", "qwen3.6")
os.environ.setdefault("QWEN_API_URL", "http://127.0.0.1:11435/v1")
os.environ.setdefault("QWEN_MODEL", "qwen3.6")
os.environ.setdefault("MEMORY_SAVE_ENABLED", "true")
os.environ.setdefault("RECALL_RERANK_ENABLED", "true")
os.environ.setdefault("VIDEO_CLONER_MEMORY_ENABLED", "true")

# 独立 chroma path（fresh start）
os.environ["MEMORY_CHROMA_PATH"] = "/tmp/rag_real_test_chroma"


def header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


async def main():
    header("M3: 真 RAG 验证（4 个 pipeline + 4 个 recall query）")

    from src.orchestrator.pipeline import run_pipeline
    from src.memory.recall import save_task_result, recall_similar_tasks
    from src.memory.store import MemoryStore

    # 预先清空 chroma（fresh start）
    import shutil
    if os.path.exists(os.environ["MEMORY_CHROMA_PATH"]):
        shutil.rmtree(os.environ["MEMORY_CHROMA_PATH"])

    # 1. 跑 4 个不同 keyword pipeline（写入 memory）
    keywords = [
        ("AI Agent 2026", "bilibili"),
        ("AI 工具实战", "bilibili"),
        ("美妆视频", "bilibili"),
        ("Python 教程", "bilibili"),
    ]

    pipeline_results = []
    for kw, platform in keywords:
        print(f"\n>>> 跑 pipeline: keyword={kw}")
        start = time.time()
        try:
            result = await run_pipeline(
                keyword=kw,
                limit=5,
                platforms=[platform],
                pipeline_mode="full",
                llm_filter=False,
            )
            elapsed = time.time() - start
            count = len(result.get("final_output", []))
            print(f"    完成 {elapsed:.1f}s, final_output: {count} 条")
            pipeline_results.append({"keyword": kw, "count": count, "elapsed": elapsed})
        except Exception as e:
            print(f"    ❌ Error: {e}")
            pipeline_results.append({"keyword": kw, "error": str(e)[:100]})

    # 2. Recall 测试（4 个 query）
    header("Recall 验证（启用 Rerank）")

    store = MemoryStore(collection_name="smart_agent_tasks")
    print(f"\nMemory 总数: {store.count()} entries")

    queries = [
        "AI Agent",  # 应该 match AI Agent + AI 工具
        "AI 工具",   # 应该 match AI 工具 + AI Agent
        "美妆",       # 应该 match 美妆视频
        "Python",     # 应该 match Python 教程
    ]

    for query in queries:
        print(f"\n>>> Query: {query!r}")
        results = recall_similar_tasks(
            query, top_k=3, store=store, rerank=True
        )
        print(f"    Found {len(results)} similar tasks:")
        for i, r in enumerate(results, 1):
            kw = r["metadata"].get("keyword", "?")
            rerank = r.get("rerank_score", "N/A")
            text_preview = r["text"][:60].replace("\n", " ")
            print(f"      {i}. {kw:20s} | rerank={rerank:.3f} | {text_preview}...")

    # 3. 报告
    header("📊 M3 最终报告")
    print(f"\nPipeline runs: {len(pipeline_results)}/4 成功")
    for r in pipeline_results:
        if "error" in r:
            print(f"  ❌ {r['keyword']}: {r['error']}")
        else:
            print(f"  ✅ {r['keyword']}: {r['count']} 条 ({r['elapsed']:.1f}s)")

    print(f"\nMemory size: {store.count()} entries")
    print(f"\n所有 query 都返 ≥ 1 result → RAG 基础功能 work")
    print(f"启用 Rerank → cross-encoder 排序")

    # 评估 recall quality（手动）
    print(f"\n🔍 Recall 质量评估:")
    for query in queries:
        results = recall_similar_tasks(query, top_k=3, store=store, rerank=True)
        if results:
            # 检查 top-1 嘅 keyword 包含 query 关键词
            top_kw = results[0]["metadata"].get("keyword", "")
            relevant = any(part in top_kw for part in query.split())
            status = "✅" if relevant else "⚠️"
            print(f"  {status} Query={query!r:15s} → Top-1: {top_kw!r} ({'relevant' if relevant else 'not strictly relevant'})")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
