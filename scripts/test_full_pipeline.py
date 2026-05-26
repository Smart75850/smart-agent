"""Full pipeline smoke test — multi-platform with DeepSeek LLM."""
import sys
sys.path.insert(0, ".")

import asyncio
from src.orchestrator.pipeline import run_pipeline
from src.utils.browser_service import browser


async def test_platform(keyword: str, platforms: list[str], limit: int = 2):
    print(f"\n{'='*60}")
    print(f"  {keyword} | {platforms} | limit={limit}")
    print(f"{'='*60}")

    result = await run_pipeline(
        keyword=keyword,
        limit=limit,
        platforms=platforms,
        pipeline_mode="full",
    )

    final = result.get("final_output", [])
    print(f"  搜索: {len(final)} 条")

    trend = result.get("trend_reports", {})
    for p, r in trend.items():
        print(f"  [TrendScout-{p}] {r.get('summary', '')[:60]}")

    prod = result.get("product_report", {})
    if prod.get("items"):
        top = prod["items"][0]
        print(f"  [ProductMiner] {top.get('name','')[:30]} | {top.get('monetization_potential',0)}分")

    vid = result.get("video_report", {})
    if vid.get("items"):
        print(f"  [VideoAnalyst] {vid.get('summary','')[:60]}")

    sent = result.get("sentiment_report", {})
    print(f"  [SentimentReader] {sent.get('summary','')[:60]}")

    copy_r = result.get("copy_report", {})
    if copy_r.get("variants"):
        print(f"  [CopyWriter] {len(copy_r['variants'])} variants | {copy_r.get('summary','')[:50]}")

    pic = result.get("visual_report", {})
    if pic.get("tactics"):
        print(f"  [PicTactic] {len(pic['tactics'])} tactics | {pic.get('summary','')[:50]}")

    remix = result.get("remix_report", {})
    print(f"  [ContentRemixer] {remix.get('summary','')[:60]}")

    # Check all 7 agent outputs present
    checks = {
        "trend_reports": bool(trend),
        "product_report": bool(prod.get("items")),
        "video_report": bool(vid.get("items")),
        "sentiment_report": bool(sent.get("summary")),
        "copy_report": bool(copy_r.get("variants")),
        "remix_report": bool(remix.get("summary")),
        "visual_report": bool(pic.get("tactics")),
    }
    passed = sum(1 for v in checks.values() if v)
    status = "PASS" if passed == 7 else f"WARN {passed}/7"
    print(f"  {status} - Agent output: {passed}/7")
    return passed == 7


async def main():
    await browser.start()
    try:
        results = []

        # B站 — 最稳定
        results.append(await test_platform("AI绘画", ["bilibili"], limit=2))

        # 抖音 — 需要 cookie 登录
        results.append(await test_platform("蓝牙耳机", ["douyin"], limit=2))

        # 小红书 — 需要 cookie 登录
        results.append(await test_platform("护肤品", ["xiaohongshu"], limit=2))

        print(f"\n{'='*60}")
        passed = sum(1 for r in results if r)
        print(f"  Platforms passed: {passed}/{len(results)}")
        if passed == len(results):
            print("  *** ALL PLATFORMS PASSED ***")
        print(f"{'='*60}")
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
