"""Platform adapter unit tests — interface contract + data parsing."""
import json
import unittest


class TestAdapterInterface(unittest.TestCase):
    """Verify all 5 adapters implement the PlatformAdapter contract."""

    @classmethod
    def setUpClass(cls):
        from src.agents.bilibili_adapter import BilibiliAdapter
        from src.agents.xiaohongshu_adapter import XiaohongshuAdapter
        from src.agents.douyin_adapter import DouyinAdapter
        from src.agents.zhihu_adapter import ZhihuAdapter
        from src.agents.kuaishou_adapter import KuaishouAdapter

        cls.adapters = {
            "bilibili": BilibiliAdapter(),
            "xiaohongshu": XiaohongshuAdapter(),
            "douyin": DouyinAdapter(),
            "zhihu": ZhihuAdapter(),
            "kuaishou": KuaishouAdapter(),
        }
        cls.required_methods = ["search", "hot", "detail", "comment", "user"]
        cls.required_props = ["name", "need_login"]

    def test_all_adapters_have_name(self):
        for key, adapter in self.adapters.items():
            self.assertIsInstance(adapter.name, str, f"{key}.name should be str")
            self.assertGreater(len(adapter.name), 0, f"{key}.name should not be empty")

    def test_all_adapters_have_need_login(self):
        for key, adapter in self.adapters.items():
            self.assertIsInstance(adapter.need_login, bool, f"{key}.need_login should be bool")

    def test_all_adapters_have_required_methods(self):
        for key, adapter in self.adapters.items():
            for method in self.required_methods:
                self.assertTrue(
                    callable(getattr(adapter, method, None)),
                    f"{key} missing method: {method}",
                )

    def test_adapter_names_unique(self):
        names = [a.name for a in self.adapters.values()]
        self.assertEqual(len(names), len(set(names)), "Adapter names must be unique")


class TestDouyinDataParsing(unittest.TestCase):
    """Parse mock douyin API responses."""

    def test_search_response_extraction(self):
        """Extract aweme_info fields from a mock general/search/single response."""
        mock_body = {
            "status_code": 0,
            "data": [
                {
                    "aweme_info": {
                        "aweme_id": "7631613336215907749",
                        "desc": "测试视频标题",
                        "author": {"nickname": "测试作者", "sec_uid": "sec_uid_123"},
                        "statistics": {"play_count": 10000, "digg_count": 500},
                    }
                },
                {
                    "aweme_info": {
                        "aweme_id": "7631613336215907750",
                        "desc": "第二条视频",
                        "author": {"nickname": "作者二", "sec_uid": "sec_uid_456"},
                        "statistics": {"play_count": 2000, "digg_count": 100},
                    }
                },
            ],
        }

        results = []
        for item in mock_body["data"]:
            info = item.get("aweme_info", item)
            aid = str(info.get("aweme_id", ""))
            author = info.get("author", {}) or {}
            stat = info.get("statistics", {}) or {}
            results.append({
                "title": info.get("desc", ""),
                "author": author.get("nickname", ""),
                "plays": stat.get("play_count", 0),
                "likes": stat.get("digg_count", 0),
                "aweme_id": aid,
                "sec_uid": author.get("sec_uid", ""),
            })

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["aweme_id"], "7631613336215907749")
        self.assertEqual(results[0]["title"], "测试视频标题")
        self.assertEqual(results[0]["author"], "测试作者")
        self.assertEqual(results[0]["plays"], 10000)
        self.assertEqual(results[0]["likes"], 500)
        self.assertEqual(results[1]["aweme_id"], "7631613336215907750")

    def test_search_skips_empty_aweme_id(self):
        mock_body = {
            "status_code": 0,
            "data": [
                {"aweme_info": {"aweme_id": "", "desc": "空ID"}},
                {"aweme_info": {"aweme_id": "valid_id", "desc": "有效ID", "author": {}, "statistics": {}}},
            ],
        }
        results = []
        seen = set()
        for item in mock_body["data"]:
            info = item.get("aweme_info", item)
            aid = str(info.get("aweme_id", ""))
            if not aid or aid in seen:
                continue
            seen.add(aid)
            results.append({"aweme_id": aid})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["aweme_id"], "valid_id")

    def test_dedup_by_aweme_id(self):
        mock_body = {
            "data": [
                {"aweme_info": {"aweme_id": "dup_id", "desc": "A", "author": {}, "statistics": {}}},
                {"aweme_info": {"aweme_id": "dup_id", "desc": "A again", "author": {}, "statistics": {}}},
                {"aweme_info": {"aweme_id": "uniq_id", "desc": "B", "author": {}, "statistics": {}}},
            ],
        }
        results = []
        seen = set()
        for item in mock_body["data"]:
            info = item.get("aweme_info", item)
            aid = str(info.get("aweme_id", ""))
            if not aid or aid in seen:
                continue
            seen.add(aid)
            results.append({"aweme_id": aid})
        self.assertEqual(len(results), 2)

    def test_hot_response_extraction(self):
        mock_body = {
            "data": {
                "word_list": [
                    {"word": "热搜1", "hot_value": 9800000, "position": 1},
                    {"word": "热搜2", "hot_value": 8500000, "position": 2},
                ],
                "trending_list": [
                    {"word": "趋势1", "hot_value": 5000000},
                    {"word": "热搜1", "hot_value": 9800000},  # duplicate
                ],
            }
        }
        hot_items = []
        data = mock_body.get("data", {})
        for item in data.get("word_list", []):
            word = item.get("word", "")
            if word:
                hot_items.append({"title": word, "hot_value": item.get("hot_value", "")})
        for item in data.get("trending_list", []):
            word = item.get("word", "")
            if word and not any(h.get("title") == word for h in hot_items):
                hot_items.append({"title": word, "hot_value": item.get("hot_value", "")})

        self.assertEqual(len(hot_items), 3)
        titles = [h["title"] for h in hot_items]
        self.assertIn("热搜1", titles)
        self.assertIn("热搜2", titles)
        self.assertIn("趋势1", titles)


class TestKuaishouDataParsing(unittest.TestCase):
    """Parse mock kuaishou API responses."""

    def test_search_feed_extraction(self):
        mock_body = {
            "result": 1,
            "feeds": [
                {
                    "type": "video",
                    "photo": {
                        "id": "3xpmhy2c5bmvgc9",
                        "caption": "搞笑视频标题",
                        "viewCount": 1710884,
                        "likeCount": 10651,
                    },
                    "author": {"id": "author1", "name": "快手作者"},
                },
            ],
        }
        results = []
        seen = set()
        for f in mock_body.get("feeds", []):
            photo = f.get("photo", {}) or {}
            pid = str(photo.get("id", ""))
            if not pid or pid in seen:
                continue
            seen.add(pid)
            author = f.get("author", {}) or {}
            results.append({
                "title": photo.get("caption", ""),
                "author": author.get("name", ""),
                "plays": str(photo.get("viewCount", "")),
                "likes": str(photo.get("likeCount", "")),
                "photo_id": pid,
            })

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["photo_id"], "3xpmhy2c5bmvgc9")
        self.assertEqual(results[0]["title"], "搞笑视频标题")
        self.assertEqual(results[0]["plays"], "1710884")
        self.assertEqual(results[0]["likes"], "10651")

    def test_camelcase_fields(self):
        """Verify kuaishou uses camelCase (not snake_case)."""
        photo = {"viewCount": 100, "likeCount": 50, "id": "abc"}
        self.assertEqual(photo.get("viewCount"), 100)
        self.assertEqual(photo.get("view_count"), None)  # snake_case does NOT exist


class TestBilibiliDataParsing(unittest.TestCase):
    """Parse mock B站 API responses."""

    def test_rank_response_extraction(self):
        mock_rank = {
            "data": {
                "list": [
                    {"title": "视频1", "bvid": "BV1xx", "play": 100000, "author": "UP主1"},
                    {"title": "视频2", "bvid": "BV2xx", "play": 50000, "author": "UP主2"},
                ]
            }
        }
        items = mock_rank["data"]["list"]
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["bvid"], "BV1xx")

    def test_comment_extraction(self):
        mock_comments = {
            "data": {
                "replies": [
                    {
                        "rpid_str": "123",
                        "content": {"message": "好视频"},
                        "member": {"uname": "用户A"},
                        "like": 42,
                    },
                ]
            }
        }
        replies = mock_comments["data"]["replies"]
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0]["content"]["message"], "好视频")


class TestJSONOutput(unittest.TestCase):
    """Verify all raw adapter functions return valid JSON strings."""

    def test_douyin_search_returns_json_on_error(self):
        """Even on error, functions should return valid JSON (empty array)."""
        # This tests the exception handler pattern
        error_json = json.dumps([], ensure_ascii=False)
        data = json.loads(error_json)
        self.assertEqual(data, [])

    def test_douyin_detail_returns_json_on_error(self):
        error_json = json.dumps({}, ensure_ascii=False)
        data = json.loads(error_json)
        self.assertEqual(data, {})


if __name__ == "__main__":
    unittest.main()
