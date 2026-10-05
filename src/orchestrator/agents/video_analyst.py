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

from typing import Literal
from pydantic import BaseModel, Field

from src.orchestrator.agents.base import BaseAgent
from src.utils.logger import logger


# ── Pydantic 结构化输出模型 ─────────────────────────────────

class VideoBreakdownOutput(BaseModel):
    index: int = Field(description="内容在输入列表中的索引")
    hook_type: Literal["数字冲击", "疑问悬念", "情感共鸣", "反直觉", "权威背书", "前后对比", "教程实用", "故事叙事", "无法判断"] = Field(description="钩子类型")
    hook_effectiveness: int = Field(ge=0, le=100, description="钩子效果评分")
    pacing: str = Field(min_length=5, description="节奏分析，含节奏变化点")
    structure_template: str = Field(description="结构模板，含阶段数命名+各阶段说明")
    conversion_point: str = Field(description="转化点，具体位置+转化动作")
    viral_mechanism: str = Field(default="", description="爆款机制，40字以上，解释为什么这个结构能传播")
    learnings: str = Field(default="", description="可复制要点，30字以上，具体操作建议")
    confidence: Literal["high", "medium", "low"] = Field(description="分析置信度")


class VideoAnalystOutput(BaseModel):
    summary: str = Field(min_length=40, description="整体结构规律，含最常见钩子类型+典型结构模式")
    breakdowns: list[VideoBreakdownOutput] = Field(description="视频结构拆解列表")


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
    learnings: str = ""             # 可複製要點（50字以上，含具體操作建議+適用平台+預期效果）


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
        summaries = []

        for p, report_dict in trend_reports.items():
            items = report_dict.get("items", [])
            if items:
                raw_items = [it.get("raw", {}) for it in items if isinstance(it, dict)]
                report = await self.run(items=raw_items[:5], platform=p)
                all_breakdowns.extend(report.items)
                if report.summary:
                    summaries.append(report.summary)

        return {"video_report": asdict(VideoReport(
            platform="all",
            total_analyzed=len(all_breakdowns),
            items=all_breakdowns,
            summary=" | ".join(summaries) if summaries else "",
        ))}

    # ── Few-Shot 示例庫（8 種鉤子類型各一例） ──────────────
    _FEWSHOT_GOOD = [
        {"hook_type": "数字冲击", "title": "3个信号告诉你房价要跌了",
         "analysis": "数字开场（3个信号）建立预期+负面情绪触发（房价跌），前3秒用新闻截图增加可信度，节奏为快剪+数据图表穿插，转化点在结尾引导关注",
         "learnings": "数字+负面情绪的组合适用于财经/民生类内容"},
        {"hook_type": "疑问悬念", "title": "为什么你做的番茄炒蛋永远不如餐厅好吃？",
         "analysis": "直接提问瞄准日常痛点，前3秒展示餐厅级vs家庭版对比画面制造认知差距，节奏为慢→快→慢（展示问题→揭示原因→总结），转化点在中段揭示秘密食材时引导收藏",
         "learnings": "提问式开头适合实用技能类，需在3秒内展示「认知差距」"},
        {"hook_type": "情感共鸣", "title": "30岁裸辞创业一年后，我终于理解了这三件事",
         "analysis": "年龄+人生转折点引发同龄人共鸣，开头用emo情绪镜头建立真实感，节奏先抑后扬（低谷→转折→成长），转化点在结尾金句引导评论互动",
         "learnings": "情感类需要真实细节支撑（具体数字/场景），避免空泛鸡汤"},
        {"hook_type": "反直觉", "title": "每天喝可乐反而瘦了10斤？医生说出真相",
         "analysis": "违反常识的命题制造好奇心缺口，开头直接展示体重对比数据，节奏: 抛反直觉→科学解释→限制条件（防误导），转化点用'但不是所有可乐都行'引导完播",
         "learnings": "反直觉必须有权威背书（医生/研究），避免沦为标题党"},
        {"hook_type": "权威背书", "title": "华为前HR总监：面试时这3句话打死不能说",
         "analysis": "大厂title建立权威感，开头直接亮身份+警告语气制造危机感，节奏为场景还原（错误示范）→正确做法对比，转化点每条规则后引导收藏'以防面试踩坑'",
         "learnings": "权威型内容需具体身份（非模糊'专家说'），场景化更有代入感"},
        {"hook_type": "前后对比", "title": "改造10平米出租屋，房东看到后直接免了一个月房租",
         "analysis": "改造前后强烈视觉冲击是核心钩子，开头0.5秒展示改造后惊艳效果再回溯过程，节奏为快放改造过程+关键步骤慢放详解，转化点在结尾展示总花费引导问'值不值'",
         "learnings": "前后对比的关键在于反差幅度，差距越大传播力越强"},
        {"hook_type": "教程实用", "title": "PPT做的丑？记住这4个快捷键，效率提升10倍",
         "analysis": "精准人群+具体痛点（PPT丑/慢），开头展示用快捷键前后的效率对比，节奏: 每个快捷键一个独立段落（5秒演示+文字标注），转化点用'第4个最实用'引导完播",
         "learnings": "教程类必须在开头展示结果，让用户知道'学了能得到什么'"},
        {"hook_type": "故事叙事", "title": "我在义乌摆摊一个月，发现了一个没人做的暴利生意",
         "analysis": "第一人称故事+地点标签（义乌）+利益承诺（暴利），开头用地摊实拍建立真实感，节奏为时间线叙事（第一周摸索→第二周发现→第三周放大），转化点用'下期讲具体怎么做'引导关注",
         "learnings": "故事类需要时间线+具体地点+真实细节，避免'我朋友说'式二手叙述"},
    ]

    _FEWSHOT_BAD = [
        {"hook_type": "无法判断", "title": "日常vlog周末在家的一天",
         "analysis": "❌ 错误示范：无明确钩子类型、开头平淡无冲突、节奏拖沓无起伏、无转化点设计，分析应坦承'此内容无明显爆款结构'而非牵强附会",
         "learnings": "平庸内容应诚实标注 confidence=low，不应强行解读"},
        {"hook_type": "数字冲击", "title": "10个小技巧",
         "analysis": "❌ 错误示范：虽有数字但无具体价值承诺（什么小技巧？对谁有用？），钩子效果极弱，分析过度夸大为'数字冲击型钩子'是错误的——真正的数字冲击需要数字+具体结果",
         "learnings": "不是有数字就是数字冲击型，必须数字+价值承诺同时成立"},
    ]

    async def _llm_generate(self, items: list, platform: str) -> VideoReport:
        """DeepSeek LLM 拆解爆款視頻結構（v2 增強 prompt）。"""
        items_text = "\n".join(
            f"{i}. {it.get('title','')} | 播放:{it.get('plays','0')} | 赞:{it.get('likes','0')}"
            for i, it in enumerate(items[:10])
        )

        good_examples_text = "\n".join(
            f"  ✅ 钩子类型: {ex['hook_type']}\n     标题: {ex['title']}\n     分析: {ex['analysis']}\n     可复制: {ex['learnings']}"
            for ex in self._FEWSHOT_GOOD
        )
        bad_examples_text = "\n".join(
            f"  ❌ 钩子类型: {ex['hook_type']}\n     标题: {ex['title']}\n     分析: {ex['analysis']}\n     教训: {ex['learnings']}"
            for ex in self._FEWSHOT_BAD
        )

        prompt = f"""<role>
你是视频结构分析师（Video Analyst）。你的唯一职责：Deconstruct 爆款视频的成功要素，Identify 开头钩子类型，Extract 可复制的结构模板。
</role>

<scope>
OWN: 钩子类型识别、节奏拆解、结构模板提取、可复制要点总结
BOUNDARY: 不评估内容是否爆款（TrendScout 的职责）、不生成文案（CopyWriter 的职责）、不分析商品（ProductMiner 的职责）
ESCALATE: 仅标题无其他数据时 → confidence=low, hook_effectiveness≤40；多标题雷同时 → 标注「同质化竞争」
</scope>

<quality_standards>
专业级输出必须满足：
1. hook_type 从9个精确枚举值中选择（数字冲击|疑问悬念|情感共鸣|反直觉|权威背书|前后对比|教程实用|故事叙事|无法判断），不可自创同义词
2. structure_template 用「模式名+N段式」格式，含各阶段说明，如「问题-解决 3段式（痛点→方案→验证）」
3. learnings 必须含具体操作步骤（「开头用数字+反直觉组合，数字不超过3个」不是「用好的标题」）
4. pacing 描述节奏变化点（「快剪→慢放→加速」不是「节奏好」）
</quality_standards>

<platform>{platform}</platform>

<examples>
{good_examples_text}
{bad_examples_text}
</examples>

<edge_cases>
仅标题无数据: confidence=low, hook_effectiveness≤40
标题雷同: 标「同质化竞争」，hook_effectiveness 扣15分
纯文字内容: pacing标「文字内容，阅读节奏」
</edge_cases>

<task>
分析以下内容的视频结构：
{items_text}
</task>

<output_format>
返回纯JSON：
{{"summary": "整体结构规律（40字以上）",
 "breakdowns": [{{"index": 数字,
   "hook_type": "枚举值之一",
   "hook_effectiveness": 0-100,
   "pacing": "节奏分析（20字以上）",
   "structure_template": "结构模板（含阶段数+各阶段说明）",
   "conversion_point": "转化点",
   "viral_mechanism": "爆款机制（20字以上）",
   "learnings": "可复制要点（20字以上）",
   "confidence": "medium/low"}}]}}
</output_format>"""

        try:
            output = await self._call_llm_with_critic(prompt, VideoAnalystOutput, "video_analyst", temperature=0.3)

            breakdowns = []
            for b in output.breakdowns:
                idx = b.index
                src = items[idx] if 0 <= idx < len(items) else {}
                breakdowns.append(VideoBreakdown(
                    title=src.get("title", ""),
                    platform=platform,
                    hook_type=b.hook_type,
                    hook_effectiveness=b.hook_effectiveness,
                    pacing=b.pacing,
                    structure_template=b.structure_template,
                    conversion_point=b.conversion_point,
                    viral_mechanism=b.viral_mechanism,
                    learnings=b.learnings,
                ))

            breakdowns.sort(key=lambda x: x.hook_effectiveness, reverse=True)
            return VideoReport(
                platform=platform,
                total_analyzed=len(breakdowns),
                items=breakdowns,
                summary=output.summary,
            )
        except Exception as exc:
            logger.warning(f"VideoAnalyst LLM 失败: {exc}")
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
            summary="LLM 不可用，降级模式",
        )
