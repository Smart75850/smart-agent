"""Ollama 7 Agent 实战测试 — Mac qwen3:32b 经 pipeline 全链路"""
import os, sys, json, asyncio, time

# 指向 Mac Ollama
os.environ["LLM_API_URL"] = "http://192.168.1.7:11434/v1"
os.environ["LLM_MODEL"] = "qwen3:32b"
os.environ.pop("DEEPSEEK_API_KEY", None)
os.environ["BROWSER_ENGINE"] = "cdp"
os.environ["PYTHONIOENCODING"] = "utf-8"

from config.settings import settings
settings.LLM_API_URL = "http://192.168.1.7:11434/v1"
settings.LLM_MODEL = "qwen3:32b"
settings.DEEPSEEK_API_KEY = ""
settings.LLM_API_KEY = ""

from src.utils.browser_service import browser

async def main():
    print("=" * 60)
    print(f"  Smart Agent - Ollama 7 Agent 全链路测试")
    print(f"  模型: {settings.LLM_MODEL}")
    print(f"  API:  {settings.LLM_API_URL}")
    print("=" * 60)

    await browser.start()

    # 跑 full pipeline on B站 (无需登录)
    from src.orchestrator import run_pipeline
    keyword = "AI工具"
    print(f"\n[启动] pipeline=full keyword={keyword} platform=bilibili")
    print("等待 qwen3:32b 逐个 Agent 处理...\n")

    t0 = time.time()
    result = await run_pipeline(
        keyword=keyword,
        limit=5,
        llm_filter=True,
        pipeline_mode="full",
        platforms=["bilibili"],
    )
    elapsed = time.time() - t0

    print(f"\n[完成] 总耗时: {elapsed:.0f}s")

    # 分析结果
    if isinstance(result, dict):
        print(f"\n结果键: {list(result.keys())}")
        for k, v in result.items():
            if isinstance(v, list):
                print(f"  {k}: {len(v)} 条")
                if v and isinstance(v[0], dict):
                    print(f"    首条键: {list(v[0].keys())[:8]}")
            elif isinstance(v, dict):
                print(f"  {k}: {len(v)} 键")
            elif isinstance(v, str):
                print(f"  {k}: {v[:100]}")
    else:
        print(f"结果类型: {type(result)}")

    await browser.close()
    print("\n✅ 全链路测试完成")

asyncio.run(main())
