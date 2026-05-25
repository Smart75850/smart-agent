import asyncio
from os import environ

from config.settings import settings
from proxy.proxy_manager import ProxyManager

ENGINE = settings.BROWSER_ENGINE
CDP_PORT = settings.CDP_PORT


class BrowserService:
    """Playwright 浏览器控制服务，全局单例。"""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._engine = None
        self._inject_cookies: dict = {}
        self._cookie_domain: str = ".douyin.com"

    async def start(self, cookies_dict: dict = None, proxy: str = None,
                    cookie_domain: str = ".douyin.com"):
        """启动浏览器（Playwright / CDP）。

        可选参数:
            cookies_dict:  账号 cookies 键值对，注入到 browser context
            proxy:         绑定 proxy URL，覆盖 ProxyManager 公共池
            cookie_domain: cookie 作用域名，默认 .douyin.com
        """
        engine = environ.get("BROWSER_ENGINE") or ENGINE
        self._engine = engine
        self._inject_cookies = cookies_dict or {}
        self._cookie_domain = cookie_domain

        if engine == "playwright":
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            launch_args: dict = {
                "headless": True,
                "args": ["--no-sandbox"],
            }
            if proxy:
                launch_args["proxy"] = {"server": proxy}
            else:
                proxy_mgr = ProxyManager()
                if proxy_mgr.enabled:
                    launch_args["proxy"] = proxy_mgr.get_playwright_proxy()

            try:
                self._browser = await self._playwright.chromium.launch(**launch_args)
            except BaseException:
                await self._cleanup()
                raise

            # 创建带 stealth 的 context
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
            )
            try:
                from playwright_stealth import Stealth
                stealth = Stealth(
                    navigator_languages_override=("zh-CN", "zh", "en"),
                    navigator_platform_override="Win32",
                    chrome_runtime=True,
                )
                await stealth.apply_stealth_async(self._context)
            except ImportError:
                pass

            # 注入 cookies（如有）
            if self._inject_cookies:
                try:
                    await self._context.add_cookies([
                        {"name": k, "value": v, "domain": self._cookie_domain, "path": "/"}
                        for k, v in self._inject_cookies.items()
                    ])
                except Exception:
                    pass

        elif engine == "cdp":
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(
                f"http://localhost:{CDP_PORT}"
            )
            self._context = self._browser.contexts[0] if self._browser.contexts else None
            if self._context and self._inject_cookies:
                try:
                    await self._context.add_cookies([
                        {"name": k, "value": v, "domain": self._cookie_domain, "path": "/"}
                        for k, v in self._inject_cookies.items()
                    ])
                except Exception:
                    pass
        else:
            raise ValueError(f"不支持的浏览器引擎: {engine}")

    @property
    def is_running(self) -> bool:
        return self._browser is not None

    async def new_page(self):
        """创建新页面（带 stealth 的 context）。"""
        if not self._browser:
            raise RuntimeError("浏览器未启动，请先调用 start()")
        if self._context:
            return await self._context.new_page()
        return await self._browser.new_page()

    async def evaluate(self, url, js, wait_selector=None):
        """打开 URL → 执行 JS → 返回结果，内部自动管理 page 生命周期。"""
        page = None
        try:
            page = await self.new_page()
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=settings.PAGE_TIMEOUT,
            )
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
            if self._context:
                await self._context.close()
                self._context = None
        except Exception:
            pass
        try:
            if self._browser:
                await self._browser.close()
        finally:
            if self._playwright:
                await self._playwright.stop()
            self._browser = None
            self._playwright = None


browser = BrowserService()
