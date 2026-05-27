"""调试贴吧搜索页 — 链接和标题详情"""
import asyncio, json, os, sys
sys.path.insert(0, ".")

os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)

from pathlib import Path
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]

        cookie_dir = Path("browser_data")
        for fp in list(cookie_dir.glob("cookies_tieba*")) + list(cookie_dir.glob("*tieba_cookies*")):
            try:
                cookies = json.loads(fp.read_text(encoding="utf-8"))
                for c in cookies:
                    try: await ctx.add_cookies([c])
                    except Exception: pass
            except Exception: pass

        page = await ctx.new_page()
        await page.goto("https://tieba.baidu.com/f/search/res?qw=AI", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        title = await page.title()
        if "安全验证" in title:
            print("!!! CAPTCHA !!!"); await browser.close(); return

        # 看所有 a 标签的 href
        all_links = await page.evaluate("""() => {
            const cards = document.querySelectorAll('[class*="threadcard"][class*="thread-new"]');
            const results = [];
            cards.forEach((card, i) => {
                if (i >= 3) return;
                const titleEl = card.querySelector('.title-wrap span') || card.querySelector('.title-wrap');
                const title = titleEl?.textContent?.trim()?.slice(0, 60) || '';
                const excerpt = card.querySelector('.abstract-wrap')?.textContent?.trim()?.slice(0, 80) || '';
                const author = card.querySelector('.forum-attention')?.textContent?.trim() || '';
                const forum = card.querySelector('.forum-name-text')?.textContent?.trim() || '';
                const replies = card.querySelector('.comment-link-zone')?.textContent?.trim() || '';
                // 找链接: item-link-bg 或任何 /p/ 链接
                const postLink = card.querySelector('a[href*="/p/"]');
                const allLinks = card.querySelectorAll('a');
                const linkInfo = Array.from(allLinks).slice(0, 5).map(a => ({
                    cls: a.className?.toString()?.slice(0, 30),
                    href: a.getAttribute('href')?.slice(0, 80),
                    text: a.textContent?.trim()?.slice(0, 30),
                }));
                results.push({title, excerpt, author, forum, replies,
                    postHref: postLink?.getAttribute('href')?.slice(0, 80),
                    links: linkInfo});
            });
            return results;
        }""")

        for i, r in enumerate(all_links):
            print(f"\n=== 卡片 {i+1} ===")
            print(f"  标题: {r['title']}")
            print(f"  摘要: {r['excerpt'][:60]}")
            print(f"  作者: {r['author']}")
            print(f"  吧名: {r['forum']}")
            print(f"  回复: {r['replies']}")
            print(f"  postHref: {r['postHref']}")
            for l in (r['links'] or [])[:4]:
                print(f"    link: [{l['cls']}] href={l['href']} text={l['text']}")

        await browser.close()


asyncio.run(main())
