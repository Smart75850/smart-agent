"""Copy Writer Agent — 生成營銷文案。

Flow:
  1. 接收 Trend Scout / Product Miner / Video Analyst 結果
  2. DeepSeek LLM 根據分析生成多版本營銷文案
  3. 輸出文案列表

用法:
  writer = CopyWriter()
  report = await writer.run(trend_items=trends, products=products, video_breakdowns=breakdowns)
"""

import json
from dataclasses import dataclass, field, asdict

from src.orchestrator.agents.base import BaseAgent
from src.utils.logger import logger


@dataclass
class CopyVariant:
    variant: str = ""
    text: str = ""
    tone: str = ""
    target_platform: str = ""


@dataclass
class CopyReport:
    keyword: str
    total_variants: int
    variants: list[CopyVariant] = field(default_factory=list)
    summary: str = ""


class CopyWriter(BaseAgent):
    """營銷文案生成 Agent。"""

    async def run(
        self,
        keyword: str = "",
        trend_items: list = None,
        products: list = None,
        video_breakdowns: list = None,
    ) -> CopyReport:
        if not self._api_key:
            return self._fallback(keyword or "通用")

        return await self._llm_generate(
            keyword=keyword,
            trend_items=trend_items or [],
            products=products or [],
            video_breakdowns=video_breakdowns or [],
        )

    async def as_node(self, state: dict) -> dict:
        keyword = state.get("keyword", "")
        trend_data = state.get("trend_reports", {})
        product_data = state.get("product_report", {})
        video_data = state.get("video_report", {})

        report = await self.run(
            keyword=keyword,
            trend_items=[it for r in trend_data.values() for it in (r.get("items", []) if isinstance(r, dict) else [])],
            products=product_data.get("items", []) if isinstance(product_data, dict) else [],
            video_breakdowns=video_data.get("items", []) if isinstance(video_data, dict) else [],
        )

        return {"copy_report": asdict(report)}

    # ── internal ──────────────────────────────────────────────

    async def _llm_generate(
        self,
        keyword: str,
        trend_items: list,
        products: list,
        video_breakdowns: list,
    ) -> CopyReport:
        context_parts = [f"核心關鍵詞: {keyword or '爆款內容'}"]
        if trend_items:
            titles = [it.get("title", it.title if hasattr(it, 'title') else "")[:40] for it in trend_items[:5]]
            context_parts.append(f"爆款趨勢: {', '.join(titles)}")
        if products:
            names = [p.get("name", p.name if hasattr(p, 'name') else "")[:30] for p in products[:5]]
            context_parts.append(f"選品: {', '.join(names)}")
        if video_breakdowns:
            hooks = [v.get("hook_type", v.hook_type if hasattr(v, 'hook_type') else "")[:20] for v in video_breakdowns[:3]]
            context_parts.append(f"爆款鉤子: {', '.join(hooks)}")

        prompt = (
            f"基於以下分析結果，生成多版本營銷文案：\n\n"
            + "\n".join(context_parts) +
            f"\n\n請返回 JSON（不要 markdown 代碼塊）：\n"
            f'{{"summary": "文案策略一句話", '
            f'"variants": [{{"variant": "headline/short/medium/long", '
            f'"text": "文案內容", "tone": "語氣風格", '
            f'"target_platform": "douyin/xiaohongshu/bilibili"}}]}}'
        )

        try:
            content = await self._call_llm(prompt, temperature=0.7, json_mode=True)
            parsed = self._parse_json(content)

            variants = [
                CopyVariant(
                    variant=v.get("variant", ""),
                    text=v.get("text", ""),
                    tone=v.get("tone", ""),
                    target_platform=v.get("target_platform", ""),
                )
                for v in parsed.get("variants", [])
            ]

            return CopyReport(
                keyword=keyword or "通用",
                total_variants=len(variants),
                variants=variants,
                summary=parsed.get("summary", ""),
            )
        except Exception as exc:
            logger.warning(f"CopyWriter LLM 失敗: {exc}")
            return self._fallback(keyword)

    def _fallback(self, keyword: str) -> CopyReport:
        return CopyReport(
            keyword=keyword,
            total_variants=1,
            variants=[CopyVariant(
                variant="short",
                text=f"🔥 爆款趨勢: {keyword}\n熱度持續上升中，把握機會！",
                tone="熱情",
                target_platform="xiaohongshu",
            )],
            summary="LLM 不可用，降級為模板文案",
        )
