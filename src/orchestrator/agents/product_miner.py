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

from typing import Literal
from pydantic import BaseModel, Field

from src.orchestrator.agents.base import BaseAgent
from src.utils.logger import logger


# ── Pydantic 结构化输出模型 ─────────────────────────────────

class ProductItemOutput(BaseModel):
    name: str = Field(description="商品名，具体品牌/型号如可识别")
    category: str = Field(description="品类")
    price_hint: str = Field(description="价格区间，如 ¥50-200")
    target_audience: str = Field(description="目标人群，年龄+场景+消费力")
    competitive_advantage: str = Field(min_length=30, description="竞争优势，含具体差异化点")
    monetization_potential: int = Field(ge=0, le=100, description="变现潜力：90+蓝海/70-89可突围/50-69红海/<50小众")
    signal_type: Literal["direct", "indirect", "no_signal"] = Field(description="信号类型")
    source_index: int = Field(description="来源内容在输入列表中的索引")


class ProductMinerOutput(BaseModel):
    summary: str = Field(min_length=40, description="整体选品趋势，含信号强度+最佳切入品类+风险提示")
    products: list[ProductItemOutput] = Field(description="商品列表")


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

    # ── Few-Shot 示例庫 ──────────────────────────────────────
    _FEWSHOT_GOOD = [
        {"signal_type": "direct", "name": "XX品牌筋膜槍",
         "monetization_potential": 88,
         "analysis": "內容直接展示+對比測評3款筋膜槍，明確提及品牌型號+價格區間，評論區多人問購買渠道；信號強度高，競爭分析：頭部品牌佔位但中腰部仍有空間",
         "advantage": "專業測評背書+精準健身人群+價格帶200-500元利潤空間可觀"},
        {"signal_type": "direct", "name": "小學生AI學習機",
         "monetization_potential": 92,
         "analysis": "內容展示孩子使用學習機的前後成績對比，明確產品功能+使用場景；家長人群付費意願強，教育硬件賽道增長快，目前頭部品牌少",
         "advantage": "教育剛需+高客單價+復購率高（多科目/多年級），藍海信號"},
        {"signal_type": "indirect", "name": "居家辦公桌面收納",
         "monetization_potential": 75,
         "analysis": "內容未直接推銷商品但展示收納前後對比，評論區大量問'在哪買''求鏈接'；indirect signal 強度中等，變現路徑為帶貨或自有品牌",
         "advantage": "需求驗證成本低+內容即素材+SKU豐富可組合銷售"},
        {"signal_type": "direct", "name": "平價藍牙耳機（¥59）",
         "monetization_potential": 65,
         "analysis": "低價位+高銷量模式，內容強調性價比對比千元耳機，但賽道擁擠（華強北+品牌降價），利潤空間薄需走量",
         "advantage": "走量模式，需差異化賣點（如電競低延遲/超長續航）才能突圍"},
        {"signal_type": "indirect", "name": "寵物自動餵食器",
         "monetization_potential": 82,
         "analysis": "內容主題為'出差3天寵物怎麼辦'，間接展示自動餵食器解決方案，評論區養寵人群活躍+多種餵食器討論；寵物經濟賽道持續增長",
         "advantage": "場景化需求明確+情感驅動消費+客單價100-500元"},
        {"signal_type": "no_signal", "name": "（無商品信號）",
         "monetization_potential": 10,
         "analysis": "純娛樂內容（搞笑段子），無任何商品/服務線索，無受眾消費意圖信號，不建議強行提取商品",
         "advantage": "誠實標註無信號比強行關聯商品更有價值"},
    ]

    _FEWSHOT_BAD = [
        {"signal_type": "no_signal", "name": "（錯誤示範）",
         "monetization_potential": 70,
         "analysis": "❌ 錯誤示範：從搞笑段子中'提取'出零食商品並給70分變現潛力——純屬臆測。內容無任何商品信號時應誠實標註，不應為了輸出而輸出",
         "advantage": "教訓：無商品信號時 monetization_potential 應 <20"},
        {"signal_type": "direct", "name": "（錯誤示範）",
         "monetization_potential": 95,
         "analysis": "❌ 錯誤示範：看到品牌名就給95分，無視該品類頭部壟斷+價格透明+利潤極薄的事實（如手機），變現潛力評估需考慮品類競爭格局",
         "advantage": "教訓：品牌露出 ≠ 高變現潛力，需分析品類競爭+利潤空間"},
    ]

    async def _llm_generate(self, items: list, keyword: str) -> ProductReport:
        """DeepSeek LLM 選品分析（v2 增強 prompt）。"""
        items_text = "\n".join(
            f"{i}. {it.get('title','')} | 作者:{it.get('author','')} | 播放:{it.get('plays','0')}"
            for i, it in enumerate(items[:15])
        )

        good_examples_text = "\n".join(
            f"  ✅ 信號: {ex['signal_type']} | 商品: {ex['name']} | 潛力分: {ex['monetization_potential']}\n     分析: {ex['analysis']}\n     優勢: {ex['advantage']}"
            for ex in self._FEWSHOT_GOOD
        )
        bad_examples_text = "\n".join(
            f"  ❌ 信號: {ex['signal_type']} | 商品: {ex['name']} | 潛力分: {ex['monetization_potential']}\n     分析: {ex['analysis']}\n     教訓: {ex['advantage']}"
            for ex in self._FEWSHOT_BAD
        )

        prompt = f"""<instructions>
你是選品分析師。從內容中識別商品信號，評估變現潛力。

強制規則：
1. signal_type 必須標註：direct（內容明確展示商品）/ indirect（暗示需求但未展示）/ no_signal（無信號）
2. competitive_advantage 必須具體（如「對比測評背書+200-500元利潤空間」），不可用「質量好」「市場大」等空泛詞
3. monetization_potential 評分要有鑑別度：90+=藍海，70-89=可突圍，50-69=紅海，<50=小眾
4. 無商品信號時返回空 products，summary 明確標註原因
5. target_audience 格式：「年齡+場景+消費力」（如「25-35歲職場女性，通勤場景，客單價200-500元」）
</instructions>

<context>
關鍵詞: {keyword or '無'}
</context>

<examples>
## 正例
{good_examples_text}

## 負例
{bad_examples_text}
</examples>

<task>
{items_text}
</task>

<output_format>
返回純JSON：
{{"summary": "選品趨勢（40字以上）",
 "products": [{{"name": "商品名", "category": "品類",
   "price_hint": "¥區間", "target_audience": "人群畫像",
   "competitive_advantage": "具體優勢（20字以上）",
   "monetization_potential": 0-100,
   "signal_type": "direct/indirect/no_signal",
   "source_index": 數字}}]}}
</output_format>"""

        try:
            output = await self._call_llm_with_critic(prompt, ProductMinerOutput, "product_miner", temperature=0.3)

            products = []
            for p in output.products:
                idx = p.source_index
                src = items[idx] if 0 <= idx < len(items) else {}
                products.append(ProductItem(
                    name=p.name,
                    category=p.category,
                    price_hint=p.price_hint,
                    target_audience=p.target_audience,
                    competitive_advantage=p.competitive_advantage,
                    monetization_potential=p.monetization_potential,
                    source_title=src.get("title", ""),
                    source_platform=src.get("platform", ""),
                ))

            products.sort(key=lambda x: x.monetization_potential, reverse=True)
            return ProductReport(
                keyword=keyword,
                total_products=len(products),
                items=products,
                summary=output.summary,
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
