"""
CDP 模式範例 — 連接真實 Chrome（小紅書/抖音/知乎需要登入）

事前：開 Chrome --remote-debugging-port=9222 並登入平台

用法：
  set BROWSER_ENGINE=cdp
  python examples/cdp_mode.py
"""
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["BROWSER_ENGINE"] = "cdp"

from src.utils.browser_service import browser
from src.agents.xiaohongshu_adapter import xiaohongshu_search
from src.agents.zhihu_adapter import zhihu_hot


async def main():
    await browser.start()

    # 知乎熱榜
    print("=== 知乎熱榜 ===")
    data = await zhihu_hot()
    print(data[:500])

    # 小紅書搜索
    print("=== 小紅書搜索 ===")
    data = await xiaohongshu_search("Python")
    print(data[:500])

    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
