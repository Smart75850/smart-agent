"""Product Miner Agent — 深入選品分析。

Flow:
  1. 接收 Trend Scout 結果 / 搜索結果
  2. DeepSeek LLM 識別商品 + 分析選品維度
  3. 輸出選品報告

用法:
  miner = ProductMiner()
  report = await miner.run(items=trend_report.items, keyword="AI")
  # LangGraph node: miner.as_node(state)
"""

import json
from dataclasses import dataclass, field, asdict

from src.orchestrator.agents.base import BaseAgent
from src.utils.logger import logger


@dataclass
class ProductItem:
    name: str                             # 商品名稱
    category: str = ""                    # 品類
    price_hint: str = ""                  # 價格區間提示
    target_audience: str = ""             # 目標人群
    competitive_advantage: str = ""       # 競爭優勢
    monetization_potential: int = 0       # 0-100 變現潛力
    source_title: str = ""                # 來源內容標題
    source_platform: str = ""             # 來源平台


@dataclass
class ProductReport:
    keyword: str
    total_products: int
    items: list[ProductItem] = field(default_factory=list)
    summary: str = ""


class ProductMiner(BaseAgent):
    """深入選品 Agent。"""

    async def run(
        self,
        items: list,
        keyword: str = "",
    ) -> ProductReport:
        """主入口：分析內容列表中的商品信號。"""
        if not items:
            return ProductReport(keyword=keyword, total_products=0, summary="無輸入數據")

        if not self._api_key:
            return self._fallback(items, keyword)

        return await self._llm_generate(items, keyword)

    async def as_node(self, state: dict) -> dict:
        """LangGraph 節點接口。"""
        trend_reports = state.get("trend_reports", {})
        merged = state.get("merged_items", [])
        all_products = []
        summaries = []

        for platform, report_dict in trend_reports.items():
            items = report_dict.get("items", [])
            if items:
                raw_items = [it.get("raw", {}) for it in items if isinstance(it, dict)]
                report = await self.run(items=raw_items or merged, keyword=state.get("keyword", ""))
                all_products.extend(report.items)
                if report.summary:
                    summaries.append(report.summary)

        return {"product_report": asdict(ProductReport(
            keyword=state.get("keyword", ""),
            total_products=len(all_products),
            items=all_products,
            summary=" | ".join(summaries) if summaries else "",
        ))}

    # ── internal ──────────────────────────────────────────────

    async def _llm_generate(self, items: list, keyword: str) -> ProductReport:
        """DeepSeek LLM 選品分析。"""
        items_text = "\n".join(
            f"{i}. {it.get('title','')} | 作者:{it.get('author','')} | 播放:{it.get('plays','0')}"
            for i, it in enumerate(items[:15])
        )

        prompt = (
            f"分析以下內容列表，識別其中提到的具體商品/產品/服務，並進行選品分析。\n\n"
            f"關鍵詞: {keyword or '無'}\n\n"
            f"{items_text}\n\n"
            f"請返回 JSON（不要 markdown 代碼塊）：\n"
            f'{{"summary": "整體選品趨勢一句話", '
            f'"products": [{{"name": "商品名", "category": "品類", '
            f'"price_hint": "價格區間", "target_audience": "目標人群", '
            f'"competitive_advantage": "競爭優勢", '
            f'"monetization_potential": 0-100, "source_index": 數字}}]}}'
        )

        try:
            content = await self._call_llm(prompt, temperature=0.3, json_mode=True)
            parsed = self._parse_json(content)

            products = []
            for p in parsed.get("products", []):
                idx = p.get("source_index", 0)
                src = items[idx] if 0 <= idx < len(items) else {}
                products.append(ProductItem(
                    name=p.get("name", ""),
                    category=p.get("category", ""),
                    price_hint=p.get("price_hint", ""),
                    target_audience=p.get("target_audience", ""),
                    competitive_advantage=p.get("competitive_advantage", ""),
                    monetization_potential=int(p.get("monetization_potential", 50)),
                    source_title=src.get("title", ""),
                    source_platform=src.get("platform", ""),
                ))

            products.sort(key=lambda x: x.monetization_potential, reverse=True)
            return ProductReport(
                keyword=keyword,
                total_products=len(products),
                items=products,
                summary=parsed.get("summary", ""),
            )

        except Exception as exc:
            logger.warning(f"ProductMiner LLM 失敗: {exc}")
            return self._fallback(items, keyword)

    def _fallback(self, items: list, keyword: str) -> ProductReport:
        """降級模式: 從標題提取關鍵詞作為商品信號。"""
        products = []
        for it in items[:10]:
            title = it.get("title", "")
            if not title:
                continue
            products.append(ProductItem(
                name=title[:40],
                category="(需 LLM 分析)",
                monetization_potential=30,
                source_title=title,
                source_platform=it.get("platform", ""),
            ))

        return ProductReport(
            keyword=keyword,
            total_products=len(products),
            items=products,
            summary="LLM 不可用，降級為標題提取",
        )
