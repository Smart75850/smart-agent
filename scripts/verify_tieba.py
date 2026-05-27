"""打开贴吧页面用于手动完成百度安全验证，完成后保存 cookie。

用法: python scripts/verify_tieba.py
完成后在另一个终端执行: echo done > browser_data/.tieba_done
或直接通知 Claude 帮你 touch 这个文件。
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from playwright.async_api import async_playwright

USER_DATA = Path("browser_data/profile").resolve()
COOKIE_DIR = Path("browser_data")
SIGNAL_FILE = COOKIE_DIR / ".tieba_done"


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

        for fp in COOKIE_DIR.glob("cookies_*.json"):
            try:
                cookies = json.loads(fp.read_text(encoding="utf-8"))
                if cookies:
                    await context.add_cookies(cookies)
            except Exception:
                pass

        page = await context.new_page()
        await page.goto(
            "https://tieba.baidu.com/f/search/res?ie=utf-8&qw=AI",
            wait_until="domcontentloaded", timeout=30000,
        )
        await page.wait_for_timeout(3000)
        print("[OK] 贴吧搜索页已打开")
        print("请在浏览器中完成滑块验证...")
        print(f"完成后，信号文件会自动保存 cookie: {SIGNAL_FILE}")
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
        tieba_cookies = [
            c for c in cookies
            if "tieba" in c.get("domain", "") or "baidu" in c.get("domain", "")
        ]
        path = COOKIE_DIR / "cookies_tieba.json"
        path.write_text(json.dumps(tieba_cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] 贴吧: {len(tieba_cookies)} cookies → {path}")

        await context.close()

    SIGNAL_FILE.unlink(missing_ok=True)
    print("完成！")


if __name__ == "__main__":
    asyncio.run(main())
