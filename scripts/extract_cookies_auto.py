"""自动从 persistent profile 提取 cookie 到 JSON（无需用户交互）"""
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

PLATFORM_PAGES = {
    "douyin":      "https://www.douyin.com/",
    "xiaohongshu": "https://www.xiaohongshu.com/explore",
    "kuaishou":    "https://www.kuaishou.com/",
    "tieba":       "https://tieba.baidu.com/",
    "bilibili":    "https://www.bilibili.com/",
    "zhihu":       "https://www.zhihu.com/",
    "weibo":       "https://weibo.com/",
}

SESSION_COOKIE_NAMES = {
    "sessionid", "SESSIONID", "passport", "token", "sid", "uid",
    "user_id", "WEBID", "PASSPORT", "PHPSESSID", "JSESSIONID",
    "auth", "AUTH", "login", "Login", "sso", "SSO", "ticket",
    "SUB", "MUSIC_U", "__ac_signature", "ac_nonce",
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
    USER_DATA.mkdir(parents=True, exist_ok=True)
    COOKIE_DIR.mkdir(exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(USER_DATA),
            headless=True,
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            args=["--no-sandbox"],
        )

        # 逐个打开平台页面，触发 cookie 加载
        for platform, url in PLATFORM_PAGES.items():
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(2000)
                await page.close()
            except Exception:
                pass

        cookies = await context.cookies()
        await context.close()

    print(f"共提取 {len(cookies)} 个 cookie")

    platform_cookies = classify_cookies(cookies)
    saved = 0
    for platform, pc in platform_cookies.items():
        path = COOKIE_DIR / f"cookies_{platform}.json"
        path.write_text(json.dumps(pc, ensure_ascii=False, indent=2), encoding="utf-8")
        names = {c["name"] for c in pc}
        sessions = names & SESSION_COOKIE_NAMES
        label = f" [关键: {sessions}]" if sessions else ""
        print(f"  [{platform}] {len(pc)} cookies → {path}{label}")
        saved += 1

    print(f"完成！{saved} 个平台。")


if __name__ == "__main__":
    asyncio.run(main())
