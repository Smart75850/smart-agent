import asyncio
from os import environ

from config.settings import settings
from proxy.proxy_manager import ProxyManager

# 模組層級常數（from config），start() 入面會再 check runtime env var override
ENGINE = settings.BROWSER_ENGINE
CDP_PORT = settings.CDP_PORT


class BrowserService:
    """Playwright 浏览器控制服务，全局单例。"""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._engine = None

    async def start(self):
        """启动浏览器（Playwright / CDP）。"""
        # 優先讀 runtime env var（main.py set 嘅仍然有效）
        engine = environ.get("BROWSER_ENGINE") or ENGINE
        self._engine = engine

        if engine == "playwright":
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            launch_args: dict = {
                "headless": True,
                "args": ["--no-sandbox"],
            }
            proxy_mgr = ProxyManager()
            if proxy_mgr.enabled:
                launch_args["proxy"] = proxy_mgr.get_playwright_proxy()
            try:
                self._browser = await self._playwright.chromium.launch(**launch_args)
            except BaseException:
                await self._cleanup()
                raise
        elif engine == "cdp":
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(
                f"http://localhost:{CDP_PORT}"
            )
        else:
            raise ValueError(f"不支持的浏览器引擎: {engine}")

    @property
    def is_running(self) -> bool:
        return self._browser is not None

    async def new_page(self):
        """创建新页面。"""
        if not self._browser:
            raise RuntimeError("浏览器未启动，请先调用 start()")
        return await self._browser.new_page()

    async def evaluate(self, url, js, wait_selector=None):
        """打开 URL → 执行 JS → 返回结果，内部自动管理 page 生命周期。"""
        page = None
        try:
            page = await self._browser.new_page()
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=settings.PAGE_TIMEOUT,
            )
            # SPA 等待：CDP 用 SLEEP_AFTER_LOAD，Playwright 等 3s
            sleep_sec = settings.SLEEP_AFTER_LOAD if self._engine == "cdp" else 3
            await asyncio.sleep(sleep_sec)
            if wait_selector:
                await page.wait_for_selector(wait_selector, timeout=settings.PAGE_TIMEOUT)
            return await page.evaluate(js)
        finally:
            if page:
                await page.close()

    async def close(self):
        """关闭浏览器并释放资源。"""
        await self._cleanup()

    async def _cleanup(self):
        try:
            if self._browser:
                await self._browser.close()
        finally:
            if self._playwright:
                await self._playwright.stop()
            self._browser = None
            self._playwright = None


# 全局单例
browser = BrowserService()
