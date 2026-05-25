"""
CDP 浏览器引擎 — 抖音搜索 & 视频详情专用
用真实浏览器（Playwright Chromium）绕过 verify_check / core_dep
"""
import asyncio
import json
import time
from urllib.parse import unquote, quote


class DouyinCDPBrowser:
    """抖音 CDP 浏览器：搜索 + 视频详情，复用浏览器实例"""

    def __init__(self, user_agent: str = "", headless: bool = True):
        self._user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        )
        self._headless = headless
        self._playwright = None
        self._browser = None
        self._context = None
        self._cookies = {}
        self._intercepted = []

    # ── 生命周期 ──────────────────────────────────────────

    async def start(self, cookies: dict = None) -> None:
        """启动浏览器并注入 Cookie"""
        if cookies:
            self._cookies = cookies
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
                "--disable-infobars",
                "--disable-dev-shm-usage",
            ],
        )
        self._context = await self._browser.new_context(
            user_agent=self._user_agent,
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )

        # playwright-stealth: 对 context 应用反检测补丁（所有新页面自动生效）
        stealth = Stealth(
            navigator_languages_override=("zh-CN", "zh", "en"),
            navigator_platform_override="Win32",
            chrome_runtime=True,
        )
        await stealth.apply_stealth_async(self._context)

        if self._cookies:
            cookie_list = []
            for name, value in self._cookies.items():
                cookie_list.append({"name": name, "value": value, "domain": ".douyin.com", "path": "/"})
            await self._context.add_cookies(cookie_list)

        # 先访问首页预热火，触发 JS 挑战完成
        page = await self._context.new_page()
        await page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        await page.close()

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._context = None
        self._playwright = None

    # ── 搜索 ──────────────────────────────────────────────

    async def search(self, keyword: str, count: int = 10) -> list[dict]:
        """CDP 浏览器搜索 — 拦截搜索页 API + 尝试一次翻页

        Douyin 搜索 API 每次只返回 ~10 条结果，count 参数仅控制截断数量。
        翻页尝试可能额外获得 1-3 条不重复结果。
        """
        if not self._context:
            raise RuntimeError("请先调用 start()")

        all_items: list[dict] = []
        seen_ids: set = set()
        first_search_url: str = ""
        search_done = asyncio.Event()
        search_page_url = f"https://www.douyin.com/search/{quote(keyword)}?type=general"

        async def on_response(response):
            nonlocal first_search_url
            if "/aweme/v1/web/general/search/stream/" not in response.url:
                return
            if response.status != 200:
                return
            if not first_search_url:
                first_search_url = response.url
                search_done.set()
            try:
                body = await response.text()
                for line in body.strip().split("\n"):
                    line = line.strip()
                    if not line.startswith("{"):
                        continue
                    data = json.loads(line)
                    for item in (data.get("data") or []):
                        aweme = item.get("aweme_info") or item
                        aweme_id = aweme.get("aweme_id", "")
                        if aweme_id and aweme_id not in seen_ids:
                            seen_ids.add(aweme_id)
                            all_items.append({
                                "aweme_id": aweme_id,
                                "desc": aweme.get("desc", "")[:200],
                                "author": (aweme.get("author") or {}).get("nickname", ""),
                                "statistics": aweme.get("statistics", {}),
                                "video_url": (aweme.get("video") or {}).get("play_addr", {}).get("url_list", [""])[0],
                            })
            except Exception:
                pass

        page = await self._context.new_page()
        page.on("response", on_response)

        await page.goto(search_page_url, wait_until="domcontentloaded", timeout=30000)
        try:
            await asyncio.wait_for(search_done.wait(), timeout=10)
        except asyncio.TimeoutError:
            pass
        await asyncio.sleep(2)

        # 尝试一次翻页（运气好能多拿 1-3 条）
        if first_search_url and len(all_items) < count:
            import re
            cursor = len(all_items)
            next_url = re.sub(r'cursor=\d+', f'cursor={cursor}', first_search_url)
            if 'cursor=' not in next_url:
                next_url += f'&cursor={cursor}'

            try:
                text_result = await page.evaluate(f"""
                (async function() {{
                    try {{
                        let resp = await fetch('{next_url}', {{
                            credentials: 'include',
                            headers: {{
                                'Accept': 'application/json, text/plain, */*',
                                'Referer': '{search_page_url}',
                            }}
                        }});
                        if (!resp.ok) return '';
                        return await resp.text();
                    }} catch(e) {{ return ''; }}
                }})()
                """)

                if text_result:
                    for line in text_result.strip().split("\n"):
                        line = line.strip()
                        if not line.startswith("{"):
                            continue
                        try:
                            data = json.loads(line)
                            for item in (data.get("data") or []):
                                aweme = item.get("aweme_info") or item
                                aweme_id = aweme.get("aweme_id", "")
                                if aweme_id and aweme_id not in seen_ids:
                                    seen_ids.add(aweme_id)
                                    all_items.append({
                                        "aweme_id": aweme_id,
                                        "desc": aweme.get("desc", "")[:200],
                                        "author": (aweme.get("author") or {}).get("nickname", ""),
                                        "statistics": aweme.get("statistics", {}),
                                        "video_url": (aweme.get("video") or {}).get("play_addr", {}).get("url_list", [""])[0],
                                    })
                        except Exception:
                            pass
            except Exception:
                pass

        await page.close()

        result = all_items[:count]
        print(f"  [CDP] 搜索「{keyword}」: {len(result)} 条（目标 {count}）")
        return result

    # ── 视频详情（SSR 抓取） ────────────────────────────

    async def get_video(self, aweme_id: str) -> dict | None:
        """从视频页面拦截 API 获取视频数据"""
        if not self._context:
            raise RuntimeError("请先调用 start()")

        video_data: dict | None = None
        done = asyncio.Event()

        async def on_response(response):
            nonlocal video_data
            url = response.url
            if "/aweme/v1/web/aweme/detail/" not in url:
                return
            if response.status != 200:
                return
            try:
                body = await response.json()
                aweme = body.get("aweme_detail") or body.get("aweme") or {}
                if aweme:
                    video_data = {
                        "aweme_id": aweme.get("aweme_id", aweme_id),
                        "desc": aweme.get("desc", ""),
                        "author": (aweme.get("author") or {}).get("nickname", ""),
                        "statistics": aweme.get("statistics", {}),
                        "video_url": (aweme.get("video") or {}).get("play_addr", {}).get("url_list", [""])[0],
                    }
                done.set()
            except Exception:
                done.set()

        page = await self._context.new_page()
        page.on("response", on_response)

        await page.goto(
            f"https://www.douyin.com/video/{aweme_id}",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        try:
            await asyncio.wait_for(done.wait(), timeout=8)
        except asyncio.TimeoutError:
            pass

        await page.close()
        return video_data


# ── 快捷函数 ──────────────────────────────────────────

async def cdp_search(keyword: str, cookies: dict, count: int = 10, headless: bool = True) -> list[dict]:
    """一站式 CDP 搜索（自动管理浏览器生命周期）"""
    browser = DouyinCDPBrowser(headless=headless)
    try:
        await browser.start(cookies)
        return await browser.search(keyword, count)
    finally:
        await browser.close()


async def cdp_video_detail(aweme_id: str, cookies: dict, headless: bool = True) -> dict | None:
    """一站式 CDP 视频详情"""
    browser = DouyinCDPBrowser(headless=headless)
    try:
        await browser.start(cookies)
        return await browser.get_video(aweme_id)
    finally:
        await browser.close()
