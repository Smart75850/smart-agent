"""调试热榜数据 — 直接跑看返回。"""
import asyncio, json, sys
sys.path.insert(0, ".")

from src.utils.browser_service import browser
from src.agents.douyin_adapter import douyin_hot
from src.agents.xiaohongshu_adapter import xiaohongshu_hot
from src.agents.zhihu_adapter import zhihu_hot


async def main():
    await browser.start()

    print("=" * 60)
    print("抖音热榜")
    print("=" * 60)
    dy = json.loads(await douyin_hot())
    print(f"共 {len(dy)} 条")
    for item in dy[:3]:
        print(json.dumps(item, ensure_ascii=False, indent=2))
    # 检查字段
    has_author = sum(1 for i in dy if i.get("author"))
    has_plays = sum(1 for i in dy if i.get("plays"))
    has_likes = sum(1 for i in dy if i.get("likes"))
    print(f"有author: {has_author}/{len(dy)}, 有plays: {has_plays}/{len(dy)}, 有likes: {has_likes}/{len(dy)}")

    print()
    print("=" * 60)
    print("小红书热榜")
    print("=" * 60)
    xhs = json.loads(await xiaohongshu_hot())
    print(f"共 {len(xhs)} 条")
    for item in xhs[:3]:
        print(json.dumps(item, ensure_ascii=False, indent=2))
    has_author = sum(1 for i in xhs if i.get("author"))
    has_plays = sum(1 for i in xhs if i.get("plays"))
    print(f"有author: {has_author}/{len(xhs)}, 有plays: {has_plays}/{len(xhs)}")

    print()
    print("=" * 60)
    print("知乎热榜")
    print("=" * 60)
    zh = json.loads(await zhihu_hot())
    print(f"共 {len(zh)} 条")
    for item in zh[:3]:
        print(json.dumps(item, ensure_ascii=False, indent=2))
    has_heat = sum(1 for i in zh if i.get("heat"))
    has_plays = sum(1 for i in zh if i.get("plays"))
    print(f"有heat: {has_heat}/{len(zh)}, 有plays: {has_plays}/{len(zh)}")

    await browser.close()


asyncio.run(main())
