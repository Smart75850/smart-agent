"""手动登录各平台 — 使用持久化浏览器，登录态自动保留。

用法:
  python scripts/login_platforms.py

浏览器会以可见模式启动，打开 4 个平台登录页。
用户在浏览器中完成登录后，关闭浏览器窗口即可。
下次启动服务时，登录态自动加载。
"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, ".")

from playwright.async_api import async_playwright
from src.utils.logger import logger

LOGIN_URLS = {
    "douyin":      "https://www.douyin.com/",
    "xiaohongshu": "https://www.xiaohongshu.com/explore",
    "kuaishou":    "https://www.kuaishou.com/",
    "tieba":       "https://tieba.baidu.com/",
}

USER_DATA = Path("browser_data/profile").resolve()


async def main():
    print("=" * 55)
    print("  平台登录助手（持久化模式）")
    print("=" * 55)
    print(f"  Profile: {USER_DATA}")
    print()
    print("  即将打开 4 个平台的登录页面：")
    for i, (p, url) in enumerate(LOGIN_URLS.items(), 1):
        print(f"    {i}. {p} → {url}")
    print()
    print("  >>> 请在浏览器中逐个完成登录（扫码/账号密码）<<<")
    print("  >>> 登录完成后，直接关闭浏览器窗口即可       <<<")
    print("  >>> 登录态会自动保留，下次无需重新登录      <<<")
    print()

    USER_DATA.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(USER_DATA),
            headless=False,
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            args=["--no-sandbox"],
        )

        pages = {}
        for p_name, url in LOGIN_URLS.items():
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)
                pages[p_name] = page
                print(f"  [OK] {p_name} 登录页已打开")
            except Exception as exc:
                print(f"  [XX] {p_name} 打开失败: {exc}")

        print()
        print(f"  已打开 {len(pages)} 个页面。请在浏览器中登录...")
        print(f"  登录完成后，关闭浏览器窗口即可。")
        print()

        # 等待用户关闭浏览器
        try:
            while True:
                try:
                    # 检查页面是否全部关闭
                    if not context.pages:
                        print("  浏览器窗口已关闭，正在保存...")
                        break
                    await asyncio.sleep(2)
                except Exception:
                    break
        except KeyboardInterrupt:
            print("\n  用户中断")

        await context.close()

    print()
    print("  登录完成！登录态已保存到 browser_data/profile/")
    print("  现在可以启动服务了: python -m api.main")


if __name__ == "__main__":
    asyncio.run(main())
