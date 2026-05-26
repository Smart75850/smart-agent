"""Pipeline integration tests — simple + full mode, agent chain, JSON parsing."""
import pytest


class TestParseJson:
    def test_normal_json(self):
        from src.orchestrator.agents.base import BaseAgent
        assert BaseAgent._parse_json('{"a": 1}') == {"a": 1}

    def test_markdown_code_block(self):
        from src.orchestrator.agents.base import BaseAgent
        assert BaseAgent._parse_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_trailing_comma(self):
        from src.orchestrator.agents.base import BaseAgent
        assert BaseAgent._parse_json('{"a": 1,}') == {"a": 1}

    def test_extra_text(self):
        from src.orchestrator.agents.base import BaseAgent
        assert BaseAgent._parse_json('text {"x": "y"} end') == {"x": "y"}

    def test_array(self):
        from src.orchestrator.agents.base import BaseAgent
        assert BaseAgent._parse_json('["a", "b",]') == ["a", "b"]

    def test_empty_object(self):
        from src.orchestrator.agents.base import BaseAgent
        assert BaseAgent._parse_json("{}") == {}

    def test_nested(self):
        from src.orchestrator.agents.base import BaseAgent
        assert BaseAgent._parse_json('{"items":[{"k":"v"}]}') == {"items": [{"k": "v"}]}


class TestGraphStructure:
    def test_all_nodes_present(self):
        from src.orchestrator.graph import build_graph
        g = build_graph()
        for name in ("search_one", "merge_results", "format_output",
                     "trend_scout", "product_miner", "video_analyst",
                     "sentiment_reader", "copy_writer", "content_remixer", "pic_tactic"):
            assert name in g.nodes, f"Missing node: {name}"

    def test_graph_compiles(self):
        from src.orchestrator.graph import compile_graph
        g = compile_graph()
        assert g is not None


class TestAgentImports:
    def test_all_agents_import(self):
        from src.orchestrator.agents import (
            TrendScout, ProductMiner, VideoAnalyst,
            SentimentReader, CopyWriter, ContentRemixer, PicTactic,
        )
        assert TrendScout is not None
        assert ProductMiner is not None
        assert VideoAnalyst is not None
        assert SentimentReader is not None
        assert CopyWriter is not None
        assert ContentRemixer is not None
        assert PicTactic is not None

    def test_base_agent_methods(self):
        from src.orchestrator.agents.base import BaseAgent
        b = BaseAgent()
        assert hasattr(b, "_call_llm")
        assert hasattr(b, "_parse_json")
        assert hasattr(b, "_api_key")

    def test_all_inherit_base(self):
        from src.orchestrator.agents.base import BaseAgent
        from src.orchestrator.agents import (
            TrendScout, ProductMiner, VideoAnalyst,
            SentimentReader, CopyWriter, ContentRemixer, PicTactic,
        )
        for cls in (TrendScout, ProductMiner, VideoAnalyst,
                    SentimentReader, CopyWriter, ContentRemixer, PicTactic):
            assert issubclass(cls, BaseAgent), f"{cls.__name__} not inheriting BaseAgent"


class TestAgentFallback:
    @pytest.mark.asyncio
    async def test_trend_scout_fallback(self):
        from src.orchestrator.agents import TrendScout
        scout = TrendScout()
        scout._api_key = ""
        items = [{"title": "test", "plays": "1000", "likes": "100", "author": "author1"}]
        report = scout._fallback("bilibili", "AI", items)
        assert report.total_candidates == 1
        assert report.summary

    @pytest.mark.asyncio
    async def test_product_miner_fallback(self):
        from src.orchestrator.agents import ProductMiner
        miner = ProductMiner()
        miner._api_key = ""
        items = [{"title": "test product", "platform": "bilibili"}]
        report = await miner.run(items=items, keyword="AI")
        assert report.total_products == 1

    @pytest.mark.asyncio
    async def test_video_analyst_fallback(self):
        from src.orchestrator.agents import VideoAnalyst
        analyst = VideoAnalyst()
        analyst._api_key = ""
        items = [{"title": "test video", "plays": "1000"}]
        report = await analyst.run(items=items, platform="bilibili")
        assert report.total_analyzed == 1

    @pytest.mark.asyncio
    async def test_sentiment_reader_fallback(self):
        from src.orchestrator.agents import SentimentReader
        reader = SentimentReader()
        reader._api_key = ""
        items = [{"title": "test", "platform_id": "123"}]
        report = await reader.run(items=items, platform="bilibili", fetch_comments=False)
        assert report.total_analyzed == 1

    @pytest.mark.asyncio
    async def test_copy_writer_fallback(self):
        from src.orchestrator.agents import CopyWriter
        writer = CopyWriter()
        writer._api_key = ""
        report = await writer.run(keyword="AI", trend_items=[{"title": "trend1"}])
        assert report.total_variants >= 1

    @pytest.mark.asyncio
    async def test_content_remixer_fallback_all_modes(self):
        from src.orchestrator.agents import ContentRemixer, RemixInput
        remixer = ContentRemixer()
        remixer._api_key = ""
        items = [{"title": "test", "platform": "bilibili"}]
        for mode in ("summarize", "analyze", "rewrite"):
            inp = RemixInput(mode=mode, topic="AI", raw_items=items)
            report = await remixer.run(inp)
            assert report.summary, f"Empty summary for mode={mode}"

    @pytest.mark.asyncio
    async def test_pic_tactic_fallback_all_modes(self):
        from src.orchestrator.agents import PicTactic
        pic = PicTactic()
        pic._api_key = ""
        for mode in ("cover", "social", "trend"):
            report = await pic.run(mode=mode, topic="AI", platform="douyin")
            assert report.total_tactics >= 1, f"No tactics for mode={mode}"


class TestPipelineSimple:
    @pytest.mark.asyncio
    async def test_simple_mode_no_results(self):
        from src.orchestrator.pipeline import run_pipeline
        from src.utils.browser_service import browser
        await browser.start()
        try:
            result = await run_pipeline(keyword="test", limit=1, platforms=["bilibili"], pipeline_mode="simple")
            assert "final_output" in result
        finally:
            await browser.close()


class TestState:
    def test_pipeline_state_fields(self):
        from src.orchestrator.state import PipelineState
        # Verify P10 fields exist on the TypedDict
        state = PipelineState(
            keyword="test", limit=10, platforms=[],
            llm_filter=False, pipeline_mode="simple",
            search_results={}, merged_items=[], filtered_items=[],
            scored_items=[], errors={}, final_output=[],
            trend_reports={}, product_report={}, video_report={},
            sentiment_report={}, copy_report={}, remix_report={}, visual_report={},
        )
        assert state["pipeline_mode"] == "simple"
        assert state["trend_reports"] == {}


class TestDownloader:
    @pytest.mark.asyncio
    async def test_import_and_dataclass(self):
        from src.downloader.media_downloader import MediaDownloader, DownloadResult
        dl = MediaDownloader()
        assert dl is not None
        r = DownloadResult(item_id="1", status="success", filepath="/tmp/x.jpg", size_bytes=1024)
        assert r.status == "success"

    @pytest.mark.asyncio
    async def test_empty_download(self):
        from src.downloader.media_downloader import MediaDownloader
        dl = MediaDownloader()
        results = await dl.download_items([], topic="test")
        assert results == []
