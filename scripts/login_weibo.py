"""打开微博登录页，扫码后保存 cookie"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from playwright.async_api import async_playwright

USER_DATA = Path("browser_data/profile").resolve()
COOKIE_DIR = Path("browser_data")
SIGNAL_FILE = COOKIE_DIR / ".weibo_done"


async def main():
    if SIGNAL_FILE.exists():
        SIGNAL_FILE.unlink()

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(USER_DATA),
            headless=False,
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            args=["--no-sandbox"],
        )

        # 注入已有 cookie
        for fp in COOKIE_DIR.glob("cookies_*.json"):
            try:
                cookies = json.loads(fp.read_text(encoding="utf-8"))
                if cookies:
                    await context.add_cookies(cookies)
            except Exception:
                pass

        page = await context.new_page()
        await page.goto("https://weibo.com/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        print("[OK] 微博首页已打开")

        print()
        print("  请在浏览器中扫码登录微博...")
        print("  登录完成后关闭浏览器窗口，或通知 Claude touch 信号文件。")
        print()

        try:
            while True:
                await asyncio.sleep(2)
                if SIGNAL_FILE.exists():
                    print("收到完成信号，正在保存 cookie...")
                    break
                if not context.pages:
                    print("浏览器被关闭，正在保存 cookie...")
                    break
        except KeyboardInterrupt:
            print("收到中断，正在保存 cookie...")

        cookies = await context.cookies()
        weibo_cookies = [c for c in cookies if "weibo" in c.get("domain", "")]
        path = COOKIE_DIR / "cookies_weibo.json"
        path.write_text(json.dumps(weibo_cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] 微博: {len(weibo_cookies)} cookies → {path}")

        await context.close()

    SIGNAL_FILE.unlink(missing_ok=True)
    print("完成！")


if __name__ == "__main__":
    asyncio.run(main())
