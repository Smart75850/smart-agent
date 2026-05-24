"""Smoke tests for Smart Agent."""

import unittest


class TestImports(unittest.TestCase):
    def test_settings(self):
        from config.settings import Settings
        s = Settings()
        self.assertEqual(s.STORE_BACKEND, "json")

    def test_constants(self):
        from constant.platform import PlatformType, CrawlType, ErrorCode
        self.assertEqual(len(list(PlatformType)), 5)
        self.assertEqual(len(list(CrawlType)), 6)

    def test_store_backends(self):
        from store import get_store
        for name in ["json", "csv", "jsonl"]:
            store = get_store(name)
            self.assertIsNotNone(store)

    def test_proxy_manager(self):
        from proxy.proxy_manager import ProxyManager
        pm = ProxyManager(proxy_list=["http://p1:8080"])
        proxy = pm.get_playwright_proxy()
        self.assertEqual(proxy, {"server": "http://p1:8080"})

    def test_cache(self):
        import asyncio
        from cache.memory_cache import MemoryCache
        c = MemoryCache()
        result = asyncio.run(c.get("missing"))
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
