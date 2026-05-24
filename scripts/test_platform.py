#!/usr/bin/env python3
"""
平台測試腳本 — 測試每個平台 adapter 能否正常爬取
用法：python scripts/test_platform.py bilibili  (或 all)
"""
import sys
import json
import asyncio

from src.utils.browser_service import browser

# 動態 import 所有 adapter
from src.agents.bilibili_adapter import bilibili_rank
from src.agents.xiaohongshu_adapter import xiaohongshu_search
from src.agents.douyin_adapter import douyin_search
from src.agents.kuaishou_adapter import kuaishou_search
from src.agents.zhihu_adapter import zhihu_hot

TESTS = {
    "bilibili": ("B站", lambda: bilibili_rank("all")),
    "xiaohongshu": ("小紅書", lambda: xiaohongshu_search("程序员")),
    "douyin": ("抖音", lambda: douyin_search("程序员")),
    "kuaishou": ("快手", lambda: kuaishou_search("程序员")),
    "zhihu": ("知乎", lambda: zhihu_hot()),
}


async def test_one(name: str):
    display, fn = TESTS[name]
    print(f"\n=== {display} ===")
    try:
        result = await fn()
        data = json.loads(result)
        print(f"✅ 成功 | 回傳 {len(data)} 項")
        if data:
            print(f"   第一項：{json.dumps(data[0], ensure_ascii=False)[:100]}")
    except Exception as e:
        print(f"❌ 失敗：{e}")


async def main():
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["all"]
    await browser.start()

    if "all" in targets:
        for name in TESTS:
            await test_one(name)
    else:
        for name in targets:
            if name in TESTS:
                await test_one(name)
            else:
                print(f"❌ 唔認識嘅平台：{name}，可選：{', '.join(TESTS.keys())}")

    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
