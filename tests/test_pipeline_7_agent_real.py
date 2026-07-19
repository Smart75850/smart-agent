"""真正 verify 7 agent 嗰 LLM call（按「主動」+「1 step 1 step」+「唔过 design」）。

策略：直接 call 每个 agent 真正嘅 _llm_generate / _generate_xxx 方法，
绕开 _collect（避免 adapter/CDP dependency），真正 trigger LLM call。

7 agent 真正 LLM 调用入口（按读完源码确认）：
  - TrendScout._llm_generate(platform, keyword, items)
  - ProductMiner._llm_generate(items, keyword)
  - VideoAnalyst._llm_generate(items, platform)
  - SentimentReader._llm_generate(items, platform, comments_data)
  - CopyWriter._llm_generate(keyword, trend_items, products, video_breakdowns)
  - ContentRemixer._generate_analyze(RemixInput(...))   # mode="analyze"
  - PicTactic._llm_generate(mode, topic, platform, trend_items, products)
"""

import asyncio
import sys
import time
import os
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Force env (含 .env)
os.environ.setdefault("LLM_API_URL", "http://127.0.0.1:11435/v1")
os.environ.setdefault("LLM_MODEL", "qwen3.6:35b-mlx")
os.environ.setdefault("DEEPSEEK_API_URL", "http://127.0.0.1:11435/v1")
os.environ.setdefault("DEEPSEEK_MODEL", "qwen3.6:35b-mlx")
os.environ.setdefault("QWEN_API_URL", "http://127.0.0.1:11435/v1")
os.environ.setdefault("QWEN_MODEL", "qwen3.6:35b-mlx")
os.environ.setdefault("LANGGRAPH_CHECKPOINT_DB", ":memory:")

# Reload settings
if "config.settings" in sys.modules:
    importlib = __import__("importlib")
    importlib.reload(sys.modules["config.settings"])

# 真实测试数据
REAL_ITEMS = [
    {"title": "我用AI做了一個能自動回覆客服的機器人，成本只花了50塊", "plays": "85万",
     "likes": "4.2万", "author": "TechGuy", "platform": "bilibili",
     "bvid": "BV1xxx1", "description": "AI Agent 实战教程"},
    {"title": "小個子女生這樣穿顯高10cm！5套通勤穿搭公式", "plays": "120万",
     "likes": "6.8万", "author": "FashionInsider", "platform": "xiaohongshu",
     "note_id": "nxxyyy", "description": "小个子穿搭"},
    {"title": "深度测评：10款AI写作工具横评", "plays": "32万",
     "likes": "1.5万", "author": "AITester", "platform": "bilibili",
     "bvid": "BV1zzz1", "description": "AI 工具测评"},
    {"title": "3個信號告訴你房價要跌了", "plays": "50万",
     "likes": "2万", "author": "FinanceAnalyst", "platform": "douyin",
     "aweme_id": "awzzz1", "description": "财经分析"},
    {"title": "為什麼你做的番茄炒蛋永遠不如餐廳好吃？", "plays": "28万",
     "likes": "1.1万", "author": "ChefMaster", "platform": "xiaohongshu",
     "note_id": "nxxxx2", "description": "美食教程"},
]


async def test_trend_scout():
    """TrendScout → _llm_generate(platform, keyword, items)."""
    from src.orchestrator.agents.trend_scout import TrendScout
    agent = TrendScout()
    print(f"  → TrendScout has _api_key: {bool(agent._api_key)}")
    report = await agent._llm_generate("bilibili", "AI Agent", REAL_ITEMS)
    return {
        "name": "TrendScout",
        "status": "OK" if report.items else "EMPTY",
        "type": type(report).__name__,
        "total": report.total_candidates,
        "summary_len": len(report.summary),
        "summary_preview": report.summary[:80],
        "top_score": max((it.viral_score for it in report.items), default=0),
    }


async def test_product_miner():
    """ProductMiner → _llm_generate(items, keyword)."""
    from src.orchestrator.agents.product_miner import ProductMiner
    agent = ProductMiner()
    print(f"  → ProductMiner has _api_key: {bool(agent._api_key)}")
    report = await agent._llm_generate(REAL_ITEMS, "AI Agent")
    return {
        "name": "ProductMiner",
        "status": "OK" if report.items else "EMPTY",
        "type": type(report).__name__,
        "total": report.total_products,
        "summary_len": len(report.summary),
        "summary_preview": report.summary[:80],
        "top_score": max((p.monetization_potential for p in report.items), default=0),
    }


async def test_video_analyst():
    """VideoAnalyst → _llm_generate(items, platform)."""
    from src.orchestrator.agents.video_analyst import VideoAnalyst
    agent = VideoAnalyst()
    print(f"  → VideoAnalyst has _api_key: {bool(agent._api_key)}")
    report = await agent._llm_generate(REAL_ITEMS, "bilibili")
    return {
        "name": "VideoAnalyst",
        "status": "OK" if report.items else "EMPTY",
        "type": type(report).__name__,
        "total": report.total_analyzed,
        "summary_len": len(report.summary),
        "summary_preview": report.summary[:80],
        "top_score": max((b.hook_effectiveness for b in report.items), default=0),
    }


async def test_sentiment_reader():
    """SentimentReader → _llm_generate(items, platform, comments_data)."""
    from src.orchestrator.agents.sentiment_reader import SentimentReader
    agent = SentimentReader()
    print(f"  → SentimentReader has _api_key: {bool(agent._api_key)}")
    # 模拟 pre-harvested comments
    comments_data = {
        "BV1xxx1": ["太强了！", "求链接", "已买", "真的好用", "价格？"],
        "nxxyyy": ["小个子救星", "已收藏", "第3套好好看"],
    }
    report = await agent._llm_generate(REAL_ITEMS, "bilibili", comments_data)
    return {
        "name": "SentimentReader",
        "status": "OK" if report.items else "EMPTY",
        "type": type(report).__name__,
        "total": report.total_analyzed,
        "summary_len": len(report.summary),
        "summary_preview": report.summary[:80],
        "overall_sentiment": report.overall_sentiment,
    }


async def test_copy_writer():
    """CopyWriter → _llm_generate(keyword, trend_items, products, video_breakdowns)."""
    from src.orchestrator.agents.copy_writer import CopyWriter
    agent = CopyWriter()
    print(f"  → CopyWriter has _api_key: {bool(agent._api_key)}")
    report = await agent._llm_generate(
        keyword="AI Agent",
        trend_items=[{"title": it["title"]} for it in REAL_ITEMS[:3]],
        products=[{"name": "AI 写作工具"}, {"name": "AI 客服机器人"}],
        video_breakdowns=[{"hook_type": "数字衝擊"}, {"hook_type": "疑問懸念"}],
    )
    return {
        "name": "CopyWriter",
        "status": "OK" if report.variants else "EMPTY",
        "type": type(report).__name__,
        "total": report.total_variants,
        "summary_len": len(report.summary),
        "summary_preview": report.summary[:80],
        "platforms": list(set(v.target_platform for v in report.variants)),
    }


async def test_content_remixer():
    """ContentRemixer → _generate_analyze(RemixInput(mode='analyze', ...))."""
    from src.orchestrator.agents.content_remixer import ContentRemixer, RemixInput
    agent = ContentRemixer()
    print(f"  → ContentRemixer has _api_key: {bool(agent._api_key)}")
    inp = RemixInput(
        mode="analyze",
        topic="AI Agent",
        raw_items=REAL_ITEMS,
    )
    report = await agent._generate_analyze(inp)
    return {
        "name": "ContentRemixer",
        "status": "OK" if report.track_insights else "EMPTY",
        "type": type(report).__name__,
        "mode": report.mode,
        "summary_len": len(report.summary),
        "summary_preview": report.summary[:80],
        "track_count": len(report.track_insights),
        "top_opportunity": max((t.opportunity_score for t in report.track_insights), default=0),
    }


async def test_pic_tactic():
    """PicTactic → _llm_generate(mode, topic, platform, trend_items, products)."""
    from src.orchestrator.agents.pic_tactic import PicTactic
    agent = PicTactic()
    print(f"  → PicTactic has _api_key: {bool(agent._api_key)}")
    report = await agent._llm_generate(
        mode="social",
        topic="AI Agent",
        platform="xiaohongshu",
        trend_items=[{"title": it["title"]} for it in REAL_ITEMS[:3]],
        products=[{"name": "AI 写作工具"}],
    )
    return {
        "name": "PicTactic",
        "status": "OK" if report.tactics else "EMPTY",
        "type": type(report).__name__,
        "mode": report.mode,
        "total": report.total_tactics,
        "summary_len": len(report.summary),
        "summary_preview": report.summary[:80],
    }


TESTS = [
    test_trend_scout,
    test_product_miner,
    test_video_analyst,
    test_sentiment_reader,
    test_copy_writer,
    test_content_remixer,
    test_pic_tactic,
]


async def main():
    print(f"=== 7 Agent 真正 LLM Call Verify (绕过 _collect) ===")
    print(f"  Settings: LLM={os.environ.get('LLM_MODEL')} URL={os.environ.get('LLM_API_URL')}\n")

    results = []
    for fn in TESTS:
        name = fn.__name__.replace("test_", "")
        start = time.time()
        try:
            r = await fn()
            r["elapsed"] = time.time() - start
            results.append(r)
            print(f"  ✅ {r['name']}: {r['status']} ({r['elapsed']:.1f}s) | {r.get('summary_preview','')[:60]}")
            for k, v in r.items():
                if k not in ("name", "status", "summary_preview"):
                    print(f"     {k}: {v}")
        except Exception as e:
            elapsed = time.time() - start
            err_result = {
                "name": name, "status": f"FAIL: {type(e).__name__}",
                "elapsed": elapsed, "error": str(e)[:300],
                "tb": traceback.format_exc()[:500],
            }
            results.append(err_result)
            print(f"  ❌ {name}: {err_result['status']} ({elapsed:.1f}s)")
            print(f"     error: {err_result['error']}")
            print(f"     tb: {err_result['tb'][:200]}")

    # Summary
    print(f"\n=== Summary ===")
    ok = sum(1 for r in results if r.get("status") == "OK")
    fail = len(results) - ok
    total_time = sum(r.get("elapsed", 0) for r in results)
    print(f"  OK: {ok}/7, FAIL: {fail}/7, Total time: {total_time:.1f}s")
    print(f"  Per-agent:")
    for r in results:
        print(f"    {r['name']}: {r['status']} ({r.get('elapsed', 0):.1f}s)")


if __name__ == "__main__":
    asyncio.run(main())