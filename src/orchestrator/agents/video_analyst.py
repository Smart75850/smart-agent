"""Video Analyst Agent — 拆解爆款視頻結構。

Flow:
  1. 接收視頻內容數據（標題/描述/評論/互動數據）
  2. DeepSeek LLM 分析：開頭鉤子/節奏/轉化點/結構模板
  3. 輸出結構化分析報告

用法:
  analyst = VideoAnalyst()
  report = await analyst.run(items=trend_items, platform="bilibili")
"""

import json
from dataclasses import dataclass, field, asdict

from src.orchestrator.agents.base import BaseAgent
from src.utils.logger import logger


@dataclass
class VideoBreakdown:
    title: str
    platform: str
    hook_type: str = ""             # 開頭鉤子類型
    hook_effectiveness: int = 0     # 0-100 鉤子效果
    pacing: str = ""                # 節奏分析
    structure_template: str = ""    # 結構模板
    conversion_point: str = ""      # 轉化點
    viral_mechanism: str = ""       # 爆款機制
    learnings: str = ""             # 可複製要點


@dataclass
class VideoReport:
    platform: str
    total_analyzed: int
    items: list[VideoBreakdown] = field(default_factory=list)
    summary: str = ""


class VideoAnalyst(BaseAgent):
    """爆款視頻結構分析 Agent。"""

    async def run(self, items: list, platform: str = "") -> VideoReport:
        if not items:
            return VideoReport(platform=platform, total_analyzed=0)

        if not self._api_key:
            return self._fallback(items, platform)

        return await self._llm_generate(items, platform)

    async def as_node(self, state: dict) -> dict:
        trend_reports = state.get("trend_reports", {})
        merged = state.get("merged_items", [])
        all_breakdowns = []

        for p, report_dict in trend_reports.items():
            items = report_dict.get("items", [])
            if items:
                raw_items = [it.get("raw", {}) for it in items if isinstance(it, dict)]
                report = await self.run(items=raw_items[:5], platform=p)
                all_breakdowns.extend(report.items)

        return {"video_report": asdict(VideoReport(
            platform="all",
            total_analyzed=len(all_breakdowns),
            items=all_breakdowns,
        ))}

    async def _llm_generate(self, items: list, platform: str) -> VideoReport:
        items_text = "\n".join(
            f"{i}. {it.get('title','')} | 播放:{it.get('plays','0')} | 讚:{it.get('likes','0')}"
            for i, it in enumerate(items[:10])
        )

        prompt = (
            f"分析以下{platform}爆款內容的視頻結構，從創作者角度拆解成功要素：\n\n"
            f"{items_text}\n\n"
            f"請返回 JSON（不要 markdown 代碼塊）：\n"
            f'{{"summary": "整體結構規律一句話", '
            f'"breakdowns": [{{"index": 數字, "hook_type": "開頭鉤子類型", '
            f'"hook_effectiveness": 0-100, "pacing": "節奏分析", '
            f'"structure_template": "結構模板", "conversion_point": "轉化點", '
            f'"viral_mechanism": "爆款機制", "learnings": "可複製要點"}}]}}'
        )

        try:
            content = await self._call_llm(prompt, temperature=0.3)
            parsed = self._parse_json(content)

            breakdowns = []
            for b in parsed.get("breakdowns", []):
                idx = b.get("index", 0)
                src = items[idx] if 0 <= idx < len(items) else {}
                breakdowns.append(VideoBreakdown(
                    title=src.get("title", ""),
                    platform=platform,
                    hook_type=b.get("hook_type", ""),
                    hook_effectiveness=int(b.get("hook_effectiveness", 50)),
                    pacing=b.get("pacing", ""),
                    structure_template=b.get("structure_template", ""),
                    conversion_point=b.get("conversion_point", ""),
                    viral_mechanism=b.get("viral_mechanism", ""),
                    learnings=b.get("learnings", ""),
                ))

            breakdowns.sort(key=lambda x: x.hook_effectiveness, reverse=True)
            return VideoReport(
                platform=platform,
                total_analyzed=len(breakdowns),
                items=breakdowns,
                summary=parsed.get("summary", ""),
            )
        except Exception as exc:
            logger.warning(f"VideoAnalyst LLM 失敗: {exc}")
            return self._fallback(items, platform)

    def _fallback(self, items: list, platform: str) -> VideoReport:
        breakdowns = [
            VideoBreakdown(
                title=it.get("title", "")[:50],
                platform=platform,
                structure_template="(需 LLM 分析)",
            )
            for it in items[:5]
        ]
        return VideoReport(
            platform=platform,
            total_analyzed=len(breakdowns),
            items=breakdowns,
            summary="LLM 不可用，降級模式",
        )
