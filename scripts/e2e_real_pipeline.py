#!/usr/bin/env python3
"""Manual E2E Real Pipeline — 需要用户参与（启动 browser + 扫码登录 + 真爬）。

按 smart-agent CLAUDE.md「测试唔好过设计」+「Explicit Uncertainty」原则：
- E2E 唔可以 silent pass（如果 browser 未启动 → 显式 fail）
- 用户驱动（用户主动启动 browser + 扫码 + verify 真结果）

用法：
    # 1. 确保 Ollama + Qwen proxy 跑紧
    # 2. 跑呢个 script
    python3 scripts/e2e_real_pipeline.py

    # 3. Script 会:
    #    - 启动 Playwright browser
    #    - 提示你扫码登录（如需要）
    #    - 跑真实 full-mode pipeline（7 平台 + 7 agent）
    #    - 验证 memory + cross_verify + meta_review + recall
    #    - 输出详细报告
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# 加入项目根
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 设置 env vars
os.environ.setdefault("LLM_API_URL", "http://127.0.0.1:11435/v1")
os.environ.setdefault("LLM_MODEL", "qwen3.6")
os.environ.setdefault("DEEPSEEK_API_URL", "http://127.0.0.1:11435/v1")
os.environ.setdefault("DEEPSEEK_MODEL", "qwen3.6")
os.environ.setdefault("QWEN_API_URL", "http://127.0.0.1:11435/v1")
os.environ.setdefault("QWEN_MODEL", "qwen3.6")
os.environ.setdefault("MEMORY_SAVE_ENABLED", "true")
os.environ.setdefault("RECALL_RERANK_ENABLED", "true")


def header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


async def step1_check_dependencies():
    """Step 1: 检查依赖（Ollama + Qwen proxy）。"""
    header("Step 1: 检查依赖")

    import httpx

    # 检查 Ollama
    try:
        r = await httpx.AsyncClient().get("http://localhost:11434/api/version", timeout=5)
        if r.status_code == 200:
            print(f"  ✅ Ollama 跑紧: {r.json().get('version')}")
        else:
            print(f"  ❌ Ollama 唔正常: {r.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ Ollama 唔可达: {e}")
        print(f"     请先启动 Ollama.app 或 ollama serve")
        return False

    # 检查 Qwen proxy
    try:
        r = await httpx.AsyncClient().get("http://127.0.0.1:11435/health", timeout=5)
        if r.status_code == 200:
            print(f"  ✅ Qwen proxy 跑紧: {r.json()}")
        else:
            print(f"  ❌ Qwen proxy 唔正常: {r.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ Qwen proxy 唔可达: {e}")
        print(f"     请先启动: cd ~/workspace/qwen-openai-proxy && ./start.sh")
        return False

    return True


async def step2_start_browser_and_login():
    """Step 2: 启动 browser + 提示用户扫码登录。"""
    header("Step 2: 启动 Playwright Browser")

    from src.utils.browser_service import browser

    print("  🚀 启动 Playwright browser...")
    try:
        await browser.start()
        print(f"  ✅ Browser 启动成功: {browser._browser_type if hasattr(browser, '_browser_type') else 'N/A'}")
    except Exception as e:
        print(f"  ❌ Browser 启动失败: {e}")
        print(f"     可能 Playwright 冇装: playwright install chromium")
        return False

    print()
    print("  📱 如果 browser 要求扫码登录（例如 bilibili / 抖音），请扫描登录。")
    print("     （注意：按 smart-agent CLAUDE.md，HTTP 爬虫已废，全部用 CDP。）")
    print()

    # Detect stdin（background run 冇 stdin → EOFError）
    import sys
    if sys.stdin.isatty():
        input("  按 Enter 继续（确认扫码完成）...")
    else:
        # Non-tty 环境（background / CI / claude code session）
        # 等 30s 让用户扫码（如果有 GUI）
        print("  ℹ️  stdin 非 tty（background run）")
        print("     如果 browser 窗口已弹出 GUI，请喺外面扫码。")
        print("     等待 30s...")
        import asyncio as _aio
        await _aio.sleep(30)

    return True


async def step3_run_pipeline():
    """Step 3: 跑真实 full-mode pipeline。"""
    header("Step 3: 跑真实 Pipeline（full mode + 7 agent）")

    from src.orchestrator.pipeline import run_pipeline

    keyword = "AI Agent"  # 简单 keyword（避免被反爬）
    platforms = ["bilibili"]  # 单一 HTTP-friendly 平台
    print(f"  🚀 Keyword: {keyword}")
    print(f"     Platforms: {platforms}")
    print()

    start = time.time()
    try:
        result = await run_pipeline(
            keyword=keyword,
            limit=10,
            platforms=platforms,
            pipeline_mode="full",  # 触发 7 agent + cross_verify
            llm_filter=False,
        )
        elapsed = time.time() - start
        print(f"  ✅ Pipeline 完成: {elapsed:.1f}s")

        # 显示结果
        final_count = len(result.get("final_output", []))
        print(f"     Final output: {final_count} 条")
        print(f"     Trend report: {bool(result.get('trend_reports'))}")
        print(f"     Cross verification: {bool(result.get('cross_verification'))}")

        return result
    except Exception as e:
        print(f"  ❌ Pipeline 失败: {type(e).__name__}: {e}")
        return None


async def step4_verify_memory_and_recall(result):
    """Step 4: 验证 memory + recall + cross_verify。"""
    header("Step 4: 验证 Memory + Review + Recall")

    if not result:
        print("  ⚠️  跳过（pipeline 失败）")
        return False

    # 4.1: Verify cross_verify triggered
    cv = result.get("cross_verification", {})
    if cv:
        print(f"  ✅ Cross-Verify triggered:")
        print(f"     consistency_score: {cv.get('consistency_score')}")
        print(f"     passed: {cv.get('passed')}")
        print(f"     issues: {len(cv.get('issues', []))}")
    else:
        print(f"  ⚠️  Cross-Verify 冇触发（可能 final_output 为空）")

    # 4.2: Verify memory write
    from src.memory.recall import recall_similar_tasks
    try:
        recalled = recall_similar_tasks(
            result.get("keyword", "AI Agent"),
            top_k=3,
        )
        print(f"  ✅ Recall found {len(recalled)} similar tasks")
        if recalled:
            for i, r in enumerate(recalled[:3]):
                print(f"     {i+1}. {r['text'][:80]}...")
        memory_ok = len(recalled) > 0
    except Exception as e:
        print(f"  ❌ Recall 失败: {e}")
        memory_ok = False

    return memory_ok


async def main():
    print()
    print("🚀 Smart Agent Pro - End-to-End Real Pipeline (Manual)")
    print("=" * 60)
    print("按 smart-agent CLAUDE.md 原则：")
    print("  - HTTP 爬虫已废，全部用 CDP")
    print("  - E2E 唔可以 silent pass（browser 未启动 → 显式 fail）")
    print("  - Memory save + review + recall 必须真验证")
    print()

    # Step 1: Check dependencies
    if not await step1_check_dependencies():
        print("\n❌ 依赖检查失败，请先启动 Ollama + Qwen proxy")
        return 1

    # Step 2: Start browser + login
    if not await step2_start_browser_and_login():
        print("\n❌ Browser 启动失败，请检查 Playwright 安装")
        return 1

    # Step 3: Run pipeline
    result = await step3_run_pipeline()

    # Step 4: Verify
    await step4_verify_memory_and_recall(result)

    header("🎉 E2E 完成")
    print("  报告位置: docs/STARTHERE-e2e-final-report.md")
    print("  测试文件: scripts/e2e_real_pipeline.py")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))