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
    hook_type: Literal["數字衝擊", "疑問懸念", "情感共鳴", "反直覺", "權威背書", "前後對比", "教程實用", "故事敍事", "無法判斷"] = Field(description="钩子类型")
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
        {"hook_type": "數字衝擊", "title": "3個信號告訴你房價要跌了",
         "analysis": "數字開場（3個信號）建立預期+負面情緒觸發（房價跌），前3秒用新聞截圖增加可信度，節奏為快剪+數據圖表穿插，轉化點在結尾引導關注",
         "learnings": "數字+負面情緒的組合適用於財經/民生類內容"},
        {"hook_type": "疑問懸念", "title": "為什麼你做的番茄炒蛋永遠不如餐廳好吃？",
         "analysis": "直接提問瞄準日常痛點，前3秒展示餐廳級vs家庭版對比畫面製造認知差距，節奏為慢→快→慢（展示問題→揭示原因→總結），轉化點在中段揭示秘密食材時引導收藏",
         "learnings": "提問式開頭適合實用技能類，需在3秒內展示「認知差距」"},
        {"hook_type": "情感共鳴", "title": "30歲裸辭創業一年後，我終於理解了這三件事",
         "analysis": "年齡+人生轉折點引發同齡人共鳴，開頭用emo情緒鏡頭建立真實感，節奏先抑後揚（低谷→轉折→成長），轉化點在結尾金句引導評論互動",
         "learnings": "情感類需要真實細節支撐（具體數字/場景），避免空泛雞湯"},
        {"hook_type": "反直覺", "title": "每天喝可樂反而瘦了10斤？醫生說出真相",
         "analysis": "違反常識的命題製造好奇心缺口，開頭直接展示體重對比數據，節奏: 拋反直覺→科學解釋→限制條件（防誤導），轉化點用'但不是所有可樂都行'引導完播",
         "learnings": "反直覺必須有權威背書（醫生/研究），避免淪為標題黨"},
        {"hook_type": "權威背書", "title": "華為前HR總監：面試時這3句話打死不能說",
         "analysis": "大廠title建立權威感，開頭直接亮身份+警告語氣製造危機感，節奏為場景還原（錯誤示範）→正確做法對比，轉化點每條規則後引導收藏'以防面試踩坑'",
         "learnings": "權威型內容需具體身份（非模糊'專家說'），場景化更有代入感"},
        {"hook_type": "前後對比", "title": "改造10平米出租屋，房東看到後直接免了一個月房租",
         "analysis": "改造前後強烈視覺衝擊是核心鉤子，開頭0.5秒展示改造後驚艷效果再回溯過程，節奏為快放改造過程+關鍵步驟慢放詳解，轉化點在結尾展示總花費引導問'值不值'",
         "learnings": "前後對比的關鍵在於反差幅度，差距越大傳播力越強"},
        {"hook_type": "教程實用", "title": "PPT做的丑？記住這4個快捷鍵，效率提升10倍",
         "analysis": "精準人群+具體痛點（PPT醜/慢），開頭展示用快捷鍵前後的效率對比，節奏: 每個快捷鍵一個獨立段落（5秒演示+文字標註），轉化點用'第4個最實用'引導完播",
         "learnings": "教程類必須在開頭展示結果，讓用戶知道'學了能得到什麼'"},
        {"hook_type": "故事敍事", "title": "我在義烏擺攤一個月，發現了一個沒人做的暴利生意",
         "analysis": "第一人稱故事+地點標籤（義烏）+利益承諾（暴利），開頭用地攤實拍建立真實感，節奏為時間線敍事（第一週摸索→第二週發現→第三週放大），轉化點用'下期講具體怎麼做'引導關注",
         "learnings": "故事類需要時間線+具體地點+真實細節，避免'我朋友說'式二手敘述"},
    ]

    _FEWSHOT_BAD = [
        {"hook_type": "無法判斷", "title": "日常vlog週末在家的一天",
         "analysis": "❌ 錯誤示範：無明確鉤子類型、開頭平淡無衝突、節奏拖沓無起伏、無轉化點設計，分析應坦承'此內容無明顯爆款結構'而非牽強附會",
         "learnings": "平庸內容應誠實標註 confidence=low，不應強行解讀"},
        {"hook_type": "數字衝擊", "title": "10個小技巧",
         "analysis": "❌ 錯誤示範：雖有數字但無具體價值承諾（什麼小技巧？對誰有用？），鉤子效果極弱，分析過度誇大為'數字衝擊型鉤子'是錯誤的——真正的數字衝擊需要數字+具體結果",
         "learnings": "不是有數字就是數字衝擊型，必須數字+價值承諾同時成立"},
    ]

    async def _llm_generate(self, items: list, platform: str) -> VideoReport:
        """DeepSeek LLM 拆解爆款視頻結構（v2 增強 prompt）。"""
        items_text = "\n".join(
            f"{i}. {it.get('title','')} | 播放:{it.get('plays','0')} | 讚:{it.get('likes','0')}"
            for i, it in enumerate(items[:10])
        )

        good_examples_text = "\n".join(
            f"  ✅ 鉤子類型: {ex['hook_type']}\n     標題: {ex['title']}\n     分析: {ex['analysis']}\n     可複製: {ex['learnings']}"
            for ex in self._FEWSHOT_GOOD
        )
        bad_examples_text = "\n".join(
            f"  ❌ 鉤子類型: {ex['hook_type']}\n     標題: {ex['title']}\n     分析: {ex['analysis']}\n     教訓: {ex['learnings']}"
            for ex in self._FEWSHOT_BAD
        )

        prompt = f"""<instructions>
你是短視頻結構分析師。基於標題和互動數據，拆解每個視頻的爆款結構。

強制規則：
1. hook_type 必須從以下9個枚舉值中精確選擇（不可自創、不可同義詞替換）：
   數字衝擊 | 疑問懸念 | 情感共鳴 | 反直覺 | 權威背書 | 前後對比 | 教程實用 | 故事敍事 | 無法判斷
2. 先判斷hook_type，再分析節奏和結構（Chain-of-Thought）
3. structure_template 用「模式名 + N段式」格式，如「問題-解決 3段式（痛點→方案→驗證）」
4. confidence 標註：有播放/點讚數據→medium；僅標題→low
5. learnings 必須具體可操作（如「開頭用數字+反直覺組合」而非「用好的標題」）
</instructions>

<context>
平台：{platform}
</context>

<examples>
## 正例（8種鉤子各一）
{good_examples_text}

## 負例
{bad_examples_text}
</examples>

<task>
分析以下內容的視頻結構：
{items_text}
</task>

<output_format>
返回純JSON：
{{"summary": "整體結構規律（40字以上）",
 "breakdowns": [{{"index": 數字,
   "hook_type": "枚舉值之一",
   "hook_effectiveness": 0-100,
   "pacing": "節奏分析（20字以上）",
   "structure_template": "結構模板（含階段數+各階段說明）",
   "conversion_point": "轉化點",
   "viral_mechanism": "爆款機制（20字以上）",
   "learnings": "可複製要點（20字以上）",
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
