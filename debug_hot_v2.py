"""调试热榜数据 — 7平台全测。"""
import asyncio, json, sys
sys.path.insert(0, ".")

from src.utils.browser_service import browser


async def test(name, func):
    print(f"\n{'='*60}")
    print(f"{name}")
    print(f"{'='*60}")
    try:
        data = json.loads(await func())
        print(f"共 {len(data)} 条")
        for item in data[:2]:
            print(json.dumps(item, ensure_ascii=False, indent=2))
        has_author = sum(1 for i in data if i.get("author"))
        has_plays  = sum(1 for i in data if i.get("plays"))
        has_likes  = sum(1 for i in data if i.get("likes"))
        has_heat   = sum(1 for i in data if i.get("heat") or i.get("hot_value"))
        print(f"author:{has_author}/{len(data)} plays:{has_plays}/{len(data)} likes:{has_likes}/{len(data)} heat:{has_heat}/{len(data)}")
    except Exception as e:
        print(f"ERROR: {e}")


async def main():
    await browser.start()

    from src.agents.douyin_adapter import douyin_hot
    from src.agents.xiaohongshu_adapter import xiaohongshu_hot
    from src.agents.zhihu_adapter import zhihu_hot
    from src.agents.kuaishou_adapter import kuaishou_hot
    from src.agents.weibo_adapter import weibo_hot
    from src.agents.tieba_adapter import tieba_hot
    from src.agents.bilibili_adapter import bilibili_rank

    await test("抖音", douyin_hot)
    await test("小红书", xiaohongshu_hot)
    await test("知乎", zhihu_hot)
    await test("快手", kuaishou_hot)
    await test("微博", weibo_hot)
    await test("贴吧", tieba_hot)

    # B站 rank 不是 async def，用 adapter
    from src.agents.bilibili_adapter import BilibiliAdapter
    async def bili_hot():
        return json.dumps([], ensure_ascii=False)
    # B站 rank 暂时跳过

    await browser.close()


asyncio.run(main())
