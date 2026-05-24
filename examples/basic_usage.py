"""
基本用法範例

用法：
  python examples/basic_usage.py
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.browser_service import browser
from src.agents.bilibili_adapter import bilibili_rank, bilibili_search


async def main():
    await browser.start()

    # B站排行榜（唔使登入）
    print("=== B站排行榜 ===")
    data = await bilibili_rank("all")
    print(data[:500])
    print()

    # B站搜索
    print("=== B站搜索 ===")
    data = await bilibili_search("Python")
    print(data[:500])

    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
