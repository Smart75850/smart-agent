"""Camoufox JS 收割器。

打开目标平台页面，拦截签名相关的 JS 文件，保存到本地缓存。
"""

import asyncio
import json
import os
import re
import time
from typing import Optional

from sign_srv.cache import CacheManager
from src.utils.logger import logger

# 各平台签名 JS 匹配规则
PLATFORM_RULES = {
    "douyin": {
        "jump_urls": ["https://www.douyin.com/search/test?keyword=test"],
        "patterns": [r"a_bogus.*\.js", r"x_bogus.*\.js", r"bogus"],
        "min_js_size": 8000,
        "js_keys": ["a_bogus", "x_bogus"],
    },
    "xiaohongshu": {
        "jump_urls": ["https://www.xiaohongshu.com/explore"],
        "patterns": [r"x-s-common.*\.js", r"xsec", r"sign"],
        "min_js_size": 50000,
        "js_keys": ["x_s_common"],
    },
    "kuaishou": {
        "jump_urls": ["https://www.kuaishou.com"],
        "patterns": [r"sign", r"security", r"encrypt"],
        "min_js_size": 5000,
        "js_keys": ["sign"],
    },
    "zhihu": {
        "jump_urls": ["https://www.zhihu.com/hot"],
        "patterns": [r"x-zse", r"web-version.*\.js"],
        "min_js_size": 10000,
        "js_keys": ["x_zse"],
    },
    "weibo": {
        "jump_urls": ["https://weibo.com/hot/search"],
        "patterns": [r"encrypt", r"sign", r"login.*\.js"],
        "min_js_size": 10000,
        "js_keys": ["encrypt"],
    },
    "tieba": {
        "jump_urls": ["https://tieba.baidu.com"],
        "patterns": [r"sign", r"security", r"jquery.*\.js"],
        "min_js_size": 3000,
        "js_keys": ["sign"],
    },
}


class JSHarvester:
    def __init__(self, cache: CacheManager = None):
        self._cache = cache or CacheManager()

    async def harvest(self, platform: str) -> Optional[dict]:
        rules = PLATFORM_RULES.get(platform)
        if not rules:
            logger.warning(f"[harvest] 未知平台: {platform}")
            return None

        logger.info(f"[harvest] 开始收割 {platform} JS...")

        try:
            from camoufox.async_api import AsyncNewBrowser
            from playwright.async_api import async_playwright

            collected: dict[str, str] = {}
            async with async_playwright() as pw:
                browser = await AsyncNewBrowser(
                    pw,
                    humanize=True,
                    block_webrtc=True,
                    geoip=True,
                    os="windows",
                    locale="zh-CN",
                )
                page = await browser.new_page()

                async def _on_response(resp):
                    url = resp.url
                    if not url.endswith(".js"):
                        return
                    body = await resp.text()
                    if not body or len(body) < rules["min_js_size"]:
                        return
                    for pattern in rules["patterns"]:
                        if re.search(pattern, url, re.IGNORECASE):
                            # 用 JS key 作为标识，取第一个匹配的
                            for key in rules["js_keys"]:
                                if key not in collected:
                                    collected[key] = body
                                    logger.info(f"[harvest] {platform} 捕获 {key}: {url[:80]} ({len(body)} chars)")
                                    break
                            break

                page.on("response", lambda resp: asyncio.ensure_future(_on_response(resp)))

                for jump_url in rules["jump_urls"]:
                    try:
                        await page.goto(jump_url, wait_until="domcontentloaded", timeout=30000)
                        await asyncio.sleep(5)
                        # 滚动触发懒加载 JS
                        for _ in range(3):
                            await page.evaluate("window.scrollBy(0, 800)")
                            await asyncio.sleep(1)
                    except Exception as exc:
                        logger.warning(f"[harvest] {platform} 页面加载失败 ({jump_url}): {exc}")

                await browser.close()

            # 保存收割结果
            saved = {}
            for key, js_code in collected.items():
                info = self._cache.save_js(platform, key, js_code)
                saved[key] = info
                logger.info(f"[harvest] {platform}/{key} 已保存: {info.get('sha256', '?')}")

            return saved if saved else None

        except ImportError:
            logger.warning("[harvest] Camoufox 不可用，跳过收割")
            return None
        except Exception as exc:
            logger.error(f"[harvest] {platform} 收割失败: {exc}")
            return None

    async def harvest_all(self) -> dict[str, Optional[dict]]:
        results = {}
        platforms = list(PLATFORM_RULES.keys())
        for platform in platforms:
            results[platform] = await self.harvest(platform)
        return results

    async def check_and_update(self, platform: str, ttl_hours: int = 24) -> bool:
        if not self._cache.is_expired(platform, ttl_hours):
            return False
        result = await self.harvest(platform)
        return result is not None

    def close(self):
        pass
