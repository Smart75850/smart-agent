"""API integration tests — FastAPI routes + request validation."""
import unittest

from fastapi.testclient import TestClient


class TestAPIRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from api.main import app
        cls.client = TestClient(app)

    def test_list_platforms(self):
        resp = self.client.get("/api/platforms")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("platforms", data)
        platforms = data["platforms"]
        self.assertGreaterEqual(len(platforms), 5)
        ids = [p["id"] for p in platforms]
        self.assertIn("bilibili", ids)
        self.assertIn("douyin", ids)
        self.assertIn("kuaishou", ids)
        self.assertIn("xiaohongshu", ids)
        self.assertIn("zhihu", ids)
        for p in platforms:
            self.assertIn("need_login", p)
            self.assertIn("types", p)

    def test_get_config(self):
        resp = self.client.get("/api/config")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("BROWSER_ENGINE", data)
        self.assertIn("CDP_PORT", data)
        self.assertIn("STORE_BACKEND", data)

    def test_crawl_validation(self):
        resp = self.client.post("/api/crawl", json={
            "platform": "bilibili",
            "type": "search",
            "keyword": "Python",
            "limit": 5,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("task_id", data)
        self.assertIsInstance(data["task_id"], str)
        self.assertGreater(len(data["task_id"]), 0)

    def test_crawl_bad_platform(self):
        """Still creates a task (validation happens in background)."""
        resp = self.client.post("/api/crawl", json={
            "platform": "nonexistent",
            "type": "search",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("task_id", data)

    def test_crawl_missing_fields(self):
        """TestClient should return 422 for missing required fields."""
        resp = self.client.post("/api/crawl", json={})
        self.assertEqual(resp.status_code, 422)

    def test_get_task_status(self):
        # First create a crawl task
        resp = self.client.post("/api/crawl", json={
            "platform": "bilibili",
            "type": "search",
            "keyword": "test",
        })
        task_id = resp.json()["task_id"]

        # Then query its status
        resp = self.client.get(f"/api/crawl/{task_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["task_id"], task_id)
        self.assertIn(data["status"], ["running", "done", "error"])

    def test_task_not_found(self):
        resp = self.client.get("/api/crawl/nonexistent-id")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("error", data)

    def test_list_data(self):
        resp = self.client.get("/api/data")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, dict)

    def test_platform_data_empty(self):
        resp = self.client.get("/api/data/nonexistent")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("data", data)
        self.assertEqual(data["data"], [])

    def test_docs_available(self):
        resp = self.client.get("/docs")
        self.assertEqual(resp.status_code, 200)

    def test_openapi_schema(self):
        resp = self.client.get("/openapi.json")
        self.assertEqual(resp.status_code, 200)
        schema = resp.json()
        self.assertEqual(schema["info"]["title"], "Smart Agent API")
        paths = list(schema["paths"].keys())
        self.assertIn("/api/platforms", paths)
        self.assertIn("/api/crawl", paths)
        self.assertIn("/api/data/{platform}", paths)
        self.assertIn("/api/data", paths)


class TestCrawlRequestModel(unittest.TestCase):
    def test_valid_minimal_request(self):
        from api.routers.crawl import CrawlRequest
        req = CrawlRequest(platform="bilibili", type="search")
        self.assertEqual(req.platform, "bilibili")
        self.assertEqual(req.type, "search")
        self.assertEqual(req.keyword, "")
        self.assertEqual(req.limit, 20)
        self.assertEqual(req.engine, "playwright")

    def test_valid_full_request(self):
        from api.routers.crawl import CrawlRequest
        req = CrawlRequest(
            platform="douyin",
            type="comment",
            keyword="7631613336215907749",
            limit=50,
            engine="cdp",
        )
        self.assertEqual(req.engine, "cdp")
        self.assertEqual(req.limit, 50)


class TestWebSocketRoute(unittest.TestCase):
    def test_ws_router_exists(self):
        from api.routers.ws import router
        self.assertIsNotNone(router)


if __name__ == "__main__":
    unittest.main()
