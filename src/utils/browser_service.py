import asyncio
import atexit
import signal
import socket
import sys
from os import environ
from pathlib import Path

from config.settings import settings
from proxy.proxy_manager import ProxyManager
from src.utils.logger import logger

_cleanup_registered = False


def _register_cleanup():
    """注册 atexit + signal 清理，确保浏览器进程不会残留。"""
    global _cleanup_registered
    if _cleanup_registered:
        return
    _cleanup_registered = True

    def _sync_cleanup():
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(browser.close())
        except Exception:
            pass

    atexit.register(_sync_cleanup)

    if sys.platform == "win32":
        try:
            signal.signal(signal.SIGBREAK, lambda *_: sys.exit(0))
        except Exception:
            pass

ENGINE = settings.BROWSER_ENGINE
CDP_PORT = settings.CDP_PORT


def _check_cdp(port: int) -> bool:
    """检测 CDP 端口是否可用。"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except (OSError, TimeoutError):
        return False


class BrowserService:
    """Playwright 浏览器控制服务，全局单例。

    引擎选择:
    - "auto": 自动检测 CDP 9222 → 有则用 CDP，无则 Playwright
    - "cdp": 强制 CDP
    - "playwright": 强制 Playwright
    """

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._engine = None
        self._inject_cookies: dict = {}
        self._cookie_domain: str = ".douyin.com"
        self._watchdog_task = None  # asyncio.Task | None

    async def start(self, cookies_dict: dict = None, proxy: str = None,
                    cookie_domain: str = ".douyin.com"):
        if self.is_running:
            return
        engine = (environ.get("BROWSER_ENGINE") or ENGINE).strip('"').strip("'")
        if engine == "auto":
            engine = "cdp" if _check_cdp(CDP_PORT) else "playwright"
            logger.info(f"浏览器引擎自动选择: {engine} (CDP={'可用' if engine == 'cdp' else '不可用'})")
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

            context_args: dict = {
                "viewport": {"width": 1280, "height": 800},
                "locale": "zh-CN",
                "timezone_id": "Asia/Shanghai",
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
            }
            if proxy:
                context_args["proxy"] = {"server": proxy}
            else:
                proxy_mgr = ProxyManager()
                if proxy_mgr.enabled:
                    context_args["proxy"] = proxy_mgr.get_playwright_proxy()

            try:
                self._browser = await self._playwright.chromium.launch(**launch_args)
                self._context = await self._browser.new_context(**context_args)
            except BaseException:
                await self._cleanup()
                raise

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
            # 必须在 playwright.start() 之前禁用代理，否则 localhost 走代理返回 502
            old_no_proxy = environ.get("no_proxy", "")
            old_NO_PROXY = environ.get("NO_PROXY", "")
            environ["no_proxy"] = "127.0.0.1,localhost"
            environ["NO_PROXY"] = "127.0.0.1,localhost"
            self._playwright = await async_playwright().start()
            try:
                self._browser = await self._playwright.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{CDP_PORT}"
                )
            finally:
                environ["no_proxy"] = old_no_proxy
                environ["NO_PROXY"] = old_NO_PROXY
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
                cf_kwargs["persistent_context"] = True

            try:
                self._browser = await AsyncNewBrowser(self._playwright, **cf_kwargs)
            except BaseException:
                await self._cleanup()
                raise

            # persistent_context 返回 BrowserContext（已有內建 context）
            if cf_kwargs.get("persistent_context"):
                self._context = self._browser
            else:
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
        _register_cleanup()
        # 取消旧 watchdog，避免 restart 时任务泄漏
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
        self._watchdog_task = asyncio.create_task(self._watchdog())

    async def _load_platform_cookies(self):
        """从 browser_data/{platform}_cookies.json 加载 cookies 并注入上下文。"""
        import json
        from pathlib import Path

        cookie_dir = Path("browser_data")
        if not cookie_dir.exists():
            return

        for filepath in list(cookie_dir.glob("cookies_*.json")) + list(cookie_dir.glob("*_cookies.json")):
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

    def is_connected(self) -> bool:
        """检查浏览器是否真正连接（非 None 且未断开）。"""
        if not self._browser:
            return False
        try:
            return self._browser.is_connected()
        except Exception:
            return False

    async def restart(self):
        """重启浏览器：清理 → 重新启动。"""
        logger.warning("浏览器断开，正在重启...")
        await self._cleanup()
        await asyncio.sleep(2)
        try:
            await self.start()
            logger.info("浏览器重启成功")
            return True
        except Exception as e:
            logger.error(f"浏览器重启失败: {e}")
            return False

    async def _watchdog(self, interval: int = 15):
        """后台监控浏览器连接，断开时自动重启。"""
        while True:
            await asyncio.sleep(interval)
            if not self.is_connected():
                await self.restart()

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
        # persistent_context 时 _browser 同 _context 系同一个对象，只能 close 一次
        is_persistent = self._browser is self._context and self._browser is not None
        try:
            if self._context:
                await self._context.close()
                self._context = None
        except Exception:
            pass
        try:
            if self._browser and not is_persistent:
                await self._browser.close()
        finally:
            if self._playwright:
                await self._playwright.stop()
            self._browser = None
            self._playwright = None


browser = BrowserService()
