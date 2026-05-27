"""登录平台 + 保存 cookie 到 JSON — 可见浏览器，登录后按 Ctrl+C 保存退出"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from playwright.async_api import async_playwright

USER_DATA = Path("browser_data/profile").resolve()
COOKIE_DIR = Path("browser_data")

PLATFORM_DOMAINS = {
    "douyin":      ["douyin.com"],
    "xiaohongshu": ["xiaohongshu.com"],
    "kuaishou":    ["kuaishou.com"],
    "tieba":       ["tieba.baidu.com"],
    "bilibili":    ["bilibili.com"],
    "zhihu":       ["zhihu.com"],
    "weibo":       ["weibo.com"],
}

LOGIN_URLS = {
    "douyin":      "https://www.douyin.com/",
    "xiaohongshu": "https://www.xiaohongshu.com/explore",
    "kuaishou":    "https://www.kuaishou.com/",
    "tieba":       "https://tieba.baidu.com/",
}


def classify_cookies(cookies):
    result = {p: [] for p in PLATFORM_DOMAINS}
    for c in cookies:
        domain = c.get("domain", "")
        for platform, domains in PLATFORM_DOMAINS.items():
            if any(d in domain for d in domains):
                result[platform].append(c)
                break
    return result


async def main():
    print("=" * 55)
    print("  平台登录助手（含 Cookie 自动保存）")
    print("=" * 55)
    print(f"  Profile: {USER_DATA}")
    print()
    print("  即将打开 4 个平台登录页面：")
    for i, (p, url) in enumerate(LOGIN_URLS.items(), 1):
        print(f"    {i}. {p} → {url}")
    print()
    print("  >>> 请在浏览器中逐个完成登录 <<<")
    print("  >>> 登录完成后回到命令行按 Ctrl+C 保存 <<<")
    print()

    USER_DATA.mkdir(parents=True, exist_ok=True)
    COOKIE_DIR.mkdir(exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(USER_DATA),
            headless=False,
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            args=["--no-sandbox"],
        )

        for p_name, url in LOGIN_URLS.items():
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)
                print(f"  [OK] {p_name} 登录页已打开")
            except Exception as exc:
                print(f"  [XX] {p_name}: {exc}")

        print()
        print(f"  请在浏览器中完成登录...完成后回到命令行按 Ctrl+C 保存。")
        print()

        try:
            while True:
                await asyncio.sleep(2)
                if not context.pages:
                    print("  浏览器已关闭，正在保存...")
                    break
        except KeyboardInterrupt:
            print("\n  正在提取 cookies...")

        cookies = await context.cookies()
        print(f"  共提取 {len(cookies)} 个 cookie")
        await context.close()

    platform_cookies = classify_cookies(cookies)

    saved = 0
    for platform, pc in platform_cookies.items():
        path = COOKIE_DIR / f"cookies_{platform}.json"
        path.write_text(json.dumps(pc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [OK] {platform}: {len(pc)} cookies → {path}")
        saved += 1

    SESSION_KEYS = {"sessionid", "SESSIONID", "login", "token", "sid", "uid", "user_id", "WEBID",
                    "passport", "PASSPORT", "PHPSESSID", "JSESSIONID", "auth", "AUTH"}
    for platform, pc in platform_cookies.items():
        names = {c["name"] for c in pc}
        found = names & SESSION_KEYS
        if found:
            print(f"  [>>] {platform} 关键 session: {found}")

    print()
    print(f"  完成！{saved} 个平台 cookie 已保存到 browser_data/")
    print(f"  现在可以启动服务: python -m api.main")


if __name__ == "__main__":
    asyncio.run(main())
