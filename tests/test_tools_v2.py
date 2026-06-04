"""Unit tests for Smart Agent v2 tools — MCP types, registry, retry policy, execution."""

import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestMCPTypes(unittest.TestCase):
    """Tests for MCP protocol dataclasses."""

    def test_01_mcptool_creation(self):
        """MCPTool creation with valid fields."""
        from tools.mcp_types import MCPTool

        tool = MCPTool(
            name="test_search",
            description="A test search tool",
            input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
        )
        self.assertEqual(tool.name, "test_search")
        self.assertEqual(tool.description, "A test search tool")
        self.assertEqual(tool.input_schema["type"], "object")
        self.assertIsNone(tool.handler)

    def test_02_mcptoolresult_defaults(self):
        """MCPToolResult defaults — content is list, is_error is False."""
        from tools.mcp_types import MCPToolResult

        result = MCPToolResult()
        self.assertEqual(result.content, [])
        self.assertFalse(result.is_error)
        self.assertEqual(result.metadata, {})

        result2 = MCPToolResult(is_error=True, metadata={"code": 500})
        self.assertTrue(result2.is_error)
        self.assertEqual(result2.metadata["code"], 500)

    def test_03_retrystrategy_defaults(self):
        """RetryStrategy defaults — 1 attempt, 0 delay, no CDP/TLS."""
        from tools.mcp_types import RetryStrategy

        s = RetryStrategy(name="test")
        self.assertEqual(s.name, "test")
        self.assertEqual(s.max_attempts, 1)
        self.assertEqual(s.delay_seconds, 0.0)
        self.assertFalse(s.use_cdp)
        self.assertFalse(s.use_tls_rotate)
        self.assertIsNone(s.handler)


class TestRegistry(unittest.TestCase):
    """Tests for ToolRegistry."""

    def test_04_register_14_tools(self):
        """After init, exactly 14 tools are registered (7 search + 7 post)."""
        from tools.registry import ToolRegistry

        reg = ToolRegistry()
        tools = reg.list_tools()
        self.assertEqual(len(tools), 14, f"Expected 14 tools (7 search + 7 post), got {len(tools)}")

    def test_05_correct_tool_names(self):
        """All 14 tools have the expected platform_name naming pattern."""
        from tools.registry import ToolRegistry

        reg = ToolRegistry()
        names = {t["name"] for t in reg.list_tools()}
        for platform in ["bilibili", "xiaohongshu", "douyin", "zhihu", "kuaishou", "weibo", "tieba"]:
            self.assertIn(f"{platform}_search", names)
            self.assertIn(f"{platform}_post", names)

    def test_06_mcp_json_format(self):
        """to_mcp_json returns name, description, inputSchema with type object."""
        from tools.registry import ToolRegistry

        reg = ToolRegistry()
        for t in reg.list_tools():
            self.assertIn("name", t)
            self.assertIn("description", t)
            self.assertIn("inputSchema", t)
            self.assertEqual(t["inputSchema"]["type"], "object")

    def test_07_unknown_tool_error(self):
        """Executing an unknown tool returns is_error=True with error content."""
        import asyncio
        from tools.registry import ToolRegistry

        async def _run():
            reg = ToolRegistry()
            return await reg.execute("nonexistent_tool", keyword="test")

        result = asyncio.run(_run())
        self.assertTrue(result.is_error)
        self.assertTrue(any("未知工具" in c.get("message", "")
                            for c in result.content if c.get("type") == "error"))

    def test_08_search_and_post_lists(self):
        """list_search_tools returns 7, list_post_tools returns 7."""
        from tools.registry import ToolRegistry

        reg = ToolRegistry()
        self.assertEqual(len(reg.list_search_tools()), 7)
        self.assertEqual(len(reg.list_post_tools()), 7)

    def test_09_post_stub_returns_not_implemented(self):
        """Post tools return is_error=True with not_implemented status."""
        import asyncio
        from tools.registry import ToolRegistry

        async def _run():
            reg = ToolRegistry()
            return await reg.execute("bilibili_post", title="測試", content="內容")

        result = asyncio.run(_run())
        self.assertTrue(result.is_error)
        self.assertEqual(result.metadata.get("status"), "not_implemented")


class TestRetryPolicy(unittest.TestCase):
    """Tests for RetryPolicy — per-platform chains."""

    def test_10_first_strategy_succeeds(self):
        """A simple http strategy has max_attempts >= 1 and no CDP."""
        from tools.retry_policy import RetryPolicy

        policy = RetryPolicy()
        strategies = policy.get_retry_for("bilibili")
        self.assertGreaterEqual(len(strategies), 1)
        first = strategies[0]
        self.assertGreaterEqual(first.max_attempts, 1)
        self.assertFalse(first.use_cdp)

    def test_11_fallback_chain(self):
        """XHS and Douyin have CDP fallback in their retry chains."""
        from tools.retry_policy import RetryPolicy

        policy = RetryPolicy()

        xhs = policy.get_retry_for("xiaohongshu")
        self.assertGreaterEqual(len(xhs), 2, "XHS should have >=2 strategies")
        xhs_cdp_names = [s.name for s in xhs if s.use_cdp]
        self.assertGreaterEqual(len(xhs_cdp_names), 1,
                                f"XHS should have CDP fallback, got: {[s.name for s in xhs]}")

        douyin = policy.get_retry_for("douyin")
        self.assertGreaterEqual(len(douyin), 2, "Douyin should have >=2 strategies")
        douyin_cdp_names = [s.name for s in douyin if s.use_cdp]
        self.assertGreaterEqual(len(douyin_cdp_names), 1,
                                f"Douyin should have CDP fallback, got: {[s.name for s in douyin]}")

        douyin_tls = [s.name for s in douyin if s.use_tls_rotate]
        self.assertGreaterEqual(len(douyin_tls), 1,
                                f"Douyin should have TLS rotate, got: {[s.name for s in douyin]}")

    def test_12_all_strategies_attempt_count(self):
        """All strategies across all platforms account for total attempt count."""
        from tools.retry_policy import RetryPolicy

        policy = RetryPolicy()

        for platform in policy.platforms:
            strategies = policy.get_retry_for(platform)
            self.assertGreater(len(strategies), 0,
                               f"{platform} has no retry strategies")

            total_attempts = sum(s.max_attempts for s in strategies)

            if platform in ("xiaohongshu", "douyin"):
                self.assertEqual(total_attempts, 4,
                                 f"{platform} total attempts should be 4, got {total_attempts}")
            else:
                self.assertEqual(total_attempts, 3,
                                 f"{platform} total attempts should be 3, got {total_attempts}")

            for s in strategies:
                self.assertGreater(s.max_attempts, 0,
                                   f"{platform}/{s.name} max_attempts must be > 0")

    def test_13_handler_map_covers_all_platforms(self):
        """Each platform in retry policy has a search handler."""
        from tools.retry_policy import RetryPolicy, _HANDLER_MAP

        policy = RetryPolicy()
        for platform in policy.platforms:
            self.assertIn(platform, _HANDLER_MAP,
                          f"{platform} missing from _HANDLER_MAP")
            self.assertIn("search", _HANDLER_MAP[platform],
                          f"{platform} missing search handler")
            self.assertTrue(callable(_HANDLER_MAP[platform]["search"]))

    def test_14_execute_unknown_platform_returns_error(self):
        """execute_with_retry for unknown platform returns is_error."""
        import asyncio
        from tools.retry_policy import RetryPolicy

        async def _run():
            policy = RetryPolicy()
            return await policy.execute_with_retry("nonexistent", "search", keyword="test")

        result = asyncio.run(_run())
        self.assertTrue(result.is_error)

    def test_15_registry_execute_with_retry_unknown_tool(self):
        """Registry execute_with_retry for unknown tool returns error."""
        import asyncio
        from tools.registry import ToolRegistry

        async def _run():
            reg = ToolRegistry()
            # 用一個存在嘅 search tool 名但 handler 會 call 外部服務
            # 改為測 unknown tool
            return await reg.execute_with_retry("not_a_real_tool", keyword="test")

        result = asyncio.run(_run())
        self.assertTrue(result.is_error)


if __name__ == "__main__":
    unittest.main()
