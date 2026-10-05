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
    competitive_advantage: str = Field(min_length=10, description="竞争优势，含具体差异化点")
    monetization_potential: int = Field(ge=0, le=100, description="变现潜力：90+蓝海/70-89可突围/50-69红海/<50小众")
    signal_type: Literal["direct", "indirect", "no_signal"] = Field(description="信号类型")
    problem_solved: str = Field(default="", description="产品解决的核心痛点（对标Apify why_winning）")
    emotional_triggers: str = Field(default="", description="触发的情绪（好奇/焦虑/渴望/FOMO/愤怒/惊喜）")
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
    problem_solved: str = ""              # 解決嘅核心痛點
    emotional_triggers: str = ""          # 觸發嘅情緒
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
            return ProductReport(keyword=keyword, total_products=0, summary="无输入数据")

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
        {"signal_type": "direct", "name": "XX品牌筋膜枪",
         "monetization_potential": 88,
         "analysis": "内容直接展示+对比测评3款筋膜枪，明确提及品牌型号+价格区间，评论区多人问购买渠道；信号强度高，竞争分析：头部品牌占位但中腰部仍有空间",
         "advantage": "专业测评背书+精准健身人群+价格带200-500元利润空间可观"},
        {"signal_type": "direct", "name": "小学生AI学习机",
         "monetization_potential": 92,
         "analysis": "内容展示孩子使用学习机的前后成绩对比，明确产品功能+使用场景；家长人群付费意愿强，教育硬件赛道增长快，目前头部品牌少",
         "advantage": "教育刚需+高客单价+复购率高（多科目/多年级），蓝海信号"},
        {"signal_type": "indirect", "name": "居家办公桌面收纳",
         "monetization_potential": 75,
         "analysis": "内容未直接推销商品但展示收纳前后对比，评论区大量问'在哪买''求链接'；indirect signal 强度中等，变现路径为带货或自有品牌",
         "advantage": "需求验证成本低+内容即素材+SKU丰富可组合销售"},
        {"signal_type": "direct", "name": "平价蓝牙耳机（¥59）",
         "monetization_potential": 65,
         "analysis": "低价位+高销量模式，内容强调性价比对比千元耳机，但赛道拥挤（华强北+品牌降价），利润空间薄需走量",
         "advantage": "走量模式，需差异化卖点（如电竞低延迟/超长续航）才能突围"},
        {"signal_type": "indirect", "name": "宠物自动喂食器",
         "monetization_potential": 82,
         "analysis": "内容主题为'出差3天宠物怎么办'，间接展示自动喂食器解决方案，评论区养宠人群活跃+多种喂食器讨论；宠物经济赛道持续增长",
         "advantage": "场景化需求明确+情感驱动消费+客单价100-500元"},
        {"signal_type": "no_signal", "name": "（无商品信号）",
         "monetization_potential": 10,
         "analysis": "纯娱乐内容（搞笑段子），无任何商品/服务线索，无受众消费意图信号，不建议强行提取商品",
         "advantage": "诚实标注无信号比强行关联商品更有价值"},
    ]

    _FEWSHOT_BAD = [
        {"signal_type": "no_signal", "name": "（错误示范）",
         "monetization_potential": 70,
         "analysis": "❌ 错误示范：从搞笑段子中'提取'出零食商品并给70分变现潜力——纯属臆测。内容无任何商品信号时应诚实标注，不应为了输出而输出",
         "advantage": "教训：无商品信号时 monetization_potential 应 <20"},
        {"signal_type": "direct", "name": "（错误示范）",
         "monetization_potential": 95,
         "analysis": "❌ 错误示范：看到品牌名就给95分，无视该品类头部垄断+价格透明+利润极薄的事实（如手机），变现潜力评估需考虑品类竞争格局",
         "advantage": "教训：品牌露出 ≠ 高变现潜力，需分析品类竞争+利润空间"},
    ]

    async def _llm_generate(self, items: list, keyword: str) -> ProductReport:
        """DeepSeek LLM 選品分析（v2 增強 prompt）。"""
        items_text = "\n".join(
            f"{i}. {it.get('title','')} | 作者:{it.get('author','')} | 播放:{it.get('plays','0')}"
            for i, it in enumerate(items[:15])
        )

        good_examples_text = "\n".join(
            f"  ✅ 信号: {ex['signal_type']} | 商品: {ex['name']} | 潜力分: {ex['monetization_potential']}\n     分析: {ex['analysis']}\n     优势: {ex['advantage']}"
            for ex in self._FEWSHOT_GOOD
        )
        bad_examples_text = "\n".join(
            f"  ❌ 信号: {ex['signal_type']} | 商品: {ex['name']} | 潜力分: {ex['monetization_potential']}\n     分析: {ex['analysis']}\n     教训: {ex['advantage']}"
            for ex in self._FEWSHOT_BAD
        )

        prompt = f"""<role>
你是选品分析师（Product Miner）。你的唯一职责：Identify 内容中的商品信号，Classify 信号类型（direct/indirect/no_signal），Evaluate 变现潜力，Extract 竞争优势。
</role>

<scope>
OWN: 商品信号识别、变现潜力评分、竞争格局分析、目标人群画像
BOUNDARY: 不评估内容是否爆款（TrendScout）、不生成文案（CopyWriter）、不分析视频结构（VideoAnalyst）
ESCALATE: 无商品信号时 → 返回空products，summary标注「此批内容无商品信号」
</scope>

<quality_standards>
专业级输出必须满足：
1. signal_type 精确标注：direct（内容展示商品/品牌）/ indirect（暗示需求）/ no_signal（无信号）
2. competitive_advantage 具象化：引用对比数据、价格区间、差异化特征；禁用「质量好」「市场大」等抽象词
3. monetization_potential 鉴别度：90+蓝海、70-89可突围、50-69红海、<50小众
4. target_audience 格式：「年龄+场景+消费力」如「25-35岁职场女性，通勤场景，客单价200-500元」
5. problem_solved: 产品解决的核心痛点（对标 Apify why_winning），如「通勤噪音焦虑」「厨房小白想做早餐但没时间」
6. emotional_triggers: 触发什么情绪驱动购买（好奇/焦虑/渴望/FOMO/愤怒/惊喜），如「怕落伍(FOMO)+价格惊喜」
</quality_standards>

<context>关键词: {keyword or '无'}</context>

<examples>
## 正例
{good_examples_text}

## 负例
{bad_examples_text}
</examples>

<task>
{items_text}
</task>

<output_format>
返回纯JSON：
{{"summary": "选品趋势（40字以上）",
 "products": [{{"name": "商品名", "category": "品类",
   "price_hint": "¥区间", "target_audience": "人群画像",
   "competitive_advantage": "具体优势（20字以上）",
   "monetization_potential": 0-100,
   "signal_type": "direct/indirect/no_signal",
   "source_index": 数字}}]}}
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
                    problem_solved=getattr(p, 'problem_solved', ''),
                    emotional_triggers=getattr(p, 'emotional_triggers', ''),
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
            logger.warning(f"ProductMiner LLM 失败: {exc}")
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
            summary="LLM 不可用，降级为标题提取",
        )
