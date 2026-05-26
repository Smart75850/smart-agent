import asyncio
from os import environ

from config.settings import settings
from proxy.proxy_manager import ProxyManager
from src.utils.logger import logger

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
        engine = environ.get("BROWSER_ENGINE") or ENGINE
        self._engine = engine
        self._inject_cookies = cookies_dict or {}
        self._cookie_domain = cookie_domain

        if engine == "playwright":
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            headless = environ.get("BROWSER_HEADLESS", "false").lower() == "true"
            launch_args: dict = {
                "headless": headless,
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
            # 临时禁用代理，避免 127.0.0.1 走代理导致 502
            old_no_proxy = environ.get("no_proxy", "")
            environ["no_proxy"] = "127.0.0.1,localhost"
            environ["NO_PROXY"] = "127.0.0.1,localhost"
            try:
                self._browser = await self._playwright.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{CDP_PORT}"
                )
            finally:
                if old_no_proxy:
                    environ["no_proxy"] = old_no_proxy
                    environ["NO_PROXY"] = old_no_proxy
            self._context = self._browser.contexts[0] if self._browser.contexts else None
            if self._context and self._inject_cookies:
                try:
                    await self._context.add_cookies([
                        {"name": k, "value": v, "domain": self._cookie_domain, "path": "/"}
                        for k, v in self._inject_cookies.items()
                    ])
                except Exception:
                    pass
        elif engine == "camoufox":
            from playwright.async_api import async_playwright
            from camoufox.async_api import AsyncNewBrowser

            self._playwright = await async_playwright().start()

            cf_kwargs: dict = {
                "headless": settings.CAMOUFOX_HEADLESS,
                "humanize": settings.CAMOUFOX_HUMANIZE,
                "block_webrtc": settings.CAMOUFOX_BLOCK_WEBRTC,
                "geoip": settings.CAMOUFOX_GEOIP,
                "locale": settings.CAMOUFOX_LOCALE,
                "os": settings.CAMOUFOX_OS or "windows",
            }

            if proxy:
                cf_kwargs["proxy"] = proxy
            else:
                proxy_mgr = ProxyManager()
                if proxy_mgr.enabled:
                    cf_kwargs["proxy"] = proxy_mgr.get_next_proxy()

            if settings.CAMOUFOX_SCREEN:
                try:
                    w, h = settings.CAMOUFOX_SCREEN.replace("x", " ").split()
                    cf_kwargs["screen"] = {"width": int(w.strip()), "height": int(h.strip())}
                except (ValueError, AttributeError):
                    pass

            if settings.CAMOUFOX_USER_DATA_DIR:
                cf_kwargs["user_data_dir"] = settings.CAMOUFOX_USER_DATA_DIR

            try:
                self._browser = await AsyncNewBrowser(self._playwright, **cf_kwargs)
            except BaseException:
                await self._cleanup()
                raise

            self._context = (
                self._browser.contexts[0]
                if self._browser.contexts
                else await self._browser.new_context()
            )

            if self._inject_cookies:
                try:
                    await self._context.add_cookies([
                        {"name": k, "value": v, "domain": self._cookie_domain, "path": "/"}
                        for k, v in self._inject_cookies.items()
                    ])
                except Exception:
                    pass

        else:
            raise ValueError(f"不支持的浏览器引擎: {engine}")

        await self._load_platform_cookies()

    async def _load_platform_cookies(self):
        """从 browser_data/{platform}_cookies.json 加载 cookies 并注入上下文。"""
        import json
        from pathlib import Path

        cookie_dir = Path("browser_data")
        if not cookie_dir.exists():
            return

        for filepath in cookie_dir.glob("*_cookies.json"):
            try:
                cookies = json.loads(filepath.read_text(encoding="utf-8"))
                if not cookies:
                    continue

                platform = filepath.stem.replace("_cookies", "")
                if self._context:
                    await self._context.add_cookies(cookies)
                    logger.info(f"CookieBridge: {platform} 注入 {len(cookies)} 个 cookie")
            except Exception:
                pass

    @property
    def is_running(self) -> bool:
        return self._browser is not None

    async def new_page(self):
        if not self._browser:
            raise RuntimeError("浏览器未启动，请先调用 start()")
        if self._context:
            return await self._context.new_page()
        return await self._browser.new_page()

    async def evaluate(self, url, js, wait_selector=None):
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
