"""PicTactic Agent — 智能配图策略。

输出 AI 生图提示词 + 视觉策略建议，不调用 Midjourney/DALL-E API。

Mode:
  cover  — 封面策略（单平台封面视觉方案）
  social — 社媒配图（多平台配图方案）
  trend  — 视觉趋势（从趋势数据提取视觉风格信号）

用法:
  pic = PicTactic()
  report = await pic.run(mode="social", topic="蓝牙耳机", platform="xiaohongshu")
"""

import json
from dataclasses import dataclass, field, asdict

from typing import Literal
from pydantic import BaseModel, Field

from src.orchestrator.agents.base import BaseAgent
from src.utils.logger import logger


# ── Pydantic 结构化输出模型 ─────────────────────────────────

class VisualTacticOutput(BaseModel):
    scene: Literal["cover", "social_post", "thumbnail", "trend"] = Field(description="场景类型")
    target_platform: Literal["douyin", "xiaohongshu", "bilibili", "zhihu", "kuaishou", "weibo", "tieba", "通用"] = Field(description="目标平台")
    style: str = Field(min_length=20, description="具体视觉风格，禁用'好看''漂亮'等模糊词")
    color_palette: str = Field(min_length=10, description="配色方案，用色彩形容词描述，禁止HEX色号")
    composition: str = Field(min_length=15, description="详细构图描述，30字以上，含比例+元素布局+文字位置")
    prompt: str = Field(min_length=30, description="英文AI生图提示词，50字以上，含主体+风格+光影+构图+画质关键词")
    rationale: str = Field(min_length=15, description="推荐理由，30字以上，结合平台用户偏好+数据依据")


class PicTacticOutput(BaseModel):
    summary: str = Field(min_length=30, description="策略总结")
    visual_trend: str = Field(default="", description="视觉趋势描述(trend模式)，80字以上")
    tactics: list[VisualTacticOutput] = Field(description="视觉策略列表")

# ── 平台降级模板 ──────────────────────────────────────────────

_PLATFORM_DEFAULTS = {
    "douyin": {
        "scene": "cover",
        "style": "商业摄影风，高对比度高饱和",
        "color_palette": "暖橙色主调搭配深灰背景，高饱和暖色冲击",
        "composition": "中心构图，大字标题占顶部1/3",
        "prompt": "eye-catching product photo, vibrant colors, trending on douyin, 9:16 aspect ratio, high contrast",
        "rationale": "抖音用户偏好高视觉冲击力封面",
    },
    "xiaohongshu": {
        "scene": "social_post",
        "style": "精致平面设计，柔和光影，平铺拍摄风格",
        "color_palette": "奶油白主调配玫瑰粉点缀，柔和粉彩色系",
        "composition": "网格布局，3:4 竖版，留白充足",
        "prompt": "aesthetic flat lay, soft pastel colors, xiaohongshu style, clean composition, 3:4 aspect ratio, natural lighting",
        "rationale": "小红书偏好精致、有质感的视觉风格",
    },
    "bilibili": {
        "scene": "cover",
        "style": "3D渲染+平面设计混合，电影感色调，信息图表元素",
        "color_palette": "深蓝紫主调搭配金色点缀，科技感冷色",
        "composition": "16:9 横版，左侧主体右侧文字",
        "prompt": "cinematic thumbnail, bold contrast, bilibili tech style, 16:9 aspect ratio, dramatic lighting, cyberpunk elements",
        "rationale": "B站用户偏好信息密度高、设计感强的封面",
    },
    "zhihu": {
        "scene": "banner",
        "style": "极简信息图表风，理性蓝灰色调，大量留白",
        "color_palette": "理性蓝灰主调配白色背景，少量橙色作为CTA强调色",
        "composition": "16:9 横版，左文右图，信息图表风",
        "prompt": "minimalist infographic style, clean typography, knowledge-sharing aesthetic, 16:9, muted blue tones, professional",
        "rationale": "知乎偏好理性、知识感的设计风格",
    },
    "kuaishou": {
        "scene": "cover",
        "style": "真实街拍风，高饱和暖色，接地气",
        "color_palette": "高饱和暖橙色主调配金黄点缀，接地气的暖色组合",
        "composition": "9:16 竖版，人物居中，标题底部",
        "prompt": "bold and authentic, street style photography, kuaishou vibe, 9:16, warm tones, relatable",
        "rationale": "快手偏好真实感、接地气的视觉风格",
    },
    "weibo": {
        "scene": "social_post",
        "style": "大胆平面设计，红暖色主调，热搜话题风",
        "color_palette": "红橙暖色主调配半透明遮罩，热搜话题风格配色",
        "composition": "1:1 方图或 3:4 竖版，文字叠加半透明遮罩，热搜话题风",
        "prompt": "bold social media graphic, red and warm tones, weibo trending style, 1:1 aspect ratio, eye-catching typography overlay, viral content aesthetic",
        "rationale": "微博偏好话题感强、有冲击力的视觉，红色系吸睛",
    },
    "tieba": {
        "scene": "banner",
        "style": "扁平插画风，蓝白配色，清爽社区感",
        "color_palette": "蓝白清新主调配浅灰背景，清爽的论坛风配色",
        "composition": "16:9 横版，左侧 logo/图标 右侧大标题，论坛风格",
        "prompt": "forum community banner, blue and white clean style, tieba aesthetic, 16:9 aspect ratio, flat design with bold title, community vibe",
        "rationale": "贴吧偏好社区感、清爽的论坛风格",
    },
}

_TREND_DEFAULT = "3D渲染 / 极简扁平 / 新中式 / Y2K复古 / 赛博朋克 — 基于文本推断（需 LLM 深度分析）"


@dataclass
class VisualTactic:
    """单条视觉策略建议。"""
    scene: str = ""
    target_platform: str = ""
    style: str = ""
    color_palette: str = ""
    composition: str = ""
    prompt: str = ""
    rationale: str = ""


@dataclass
class VisualReport:
    topic: str
    mode: str
    platform: str = ""
    total_tactics: int = 0
    tactics: list[VisualTactic] = field(default_factory=list)
    visual_trend: str = ""
    summary: str = ""


class PicTactic(BaseAgent):
    """智能配图策略 Agent。"""

    async def run(
        self,
        mode: str = "social",
        topic: str = "",
        platform: str = "",
        trend_items: list = None,
        products: list = None,
    ) -> VisualReport:
        if not self._api_key:
            return self._fallback(mode, topic, platform, trend_items, products)

        return await self._llm_generate(mode, topic, platform, trend_items or [], products or [])

    async def as_node(self, state: dict) -> dict:
        keyword = state.get("keyword", "")
        trend_data = state.get("trend_reports", {})
        product_data = state.get("product_report", {})

        trend_items = []
        for r in trend_data.values():
            items = r.get("items", []) if isinstance(r, dict) else []
            trend_items.extend(items)

        products = product_data.get("items", []) if isinstance(product_data, dict) else []

        report = await self.run(
            mode="social",
            topic=keyword,
            trend_items=trend_items,
            products=products,
        )

        return {"visual_report": asdict(report)}

    # ── internal ──────────────────────────────────────────────

    # ── Few-Shot 示例庫（5 good + 2 bad） ──────────────────
    _FEWSHOT_GOOD = [
        {"mode": "cover", "platform": "douyin", "topic": "藍牙耳機評測",
         "output": {"summary": "抖音封面核心是高視覺衝擊力+大字標題，暖色系+中心構圖是點擊率最高的組合",
                    "tactic": {"scene": "cover", "target_platform": "douyin",
                               "style": "商業攝影風，高對比度高飽和，產品置於視覺中心",
                               "color_palette": "暖橙色主調搭配深灰背景，高飽和暖色衝擊",
                               "composition": "9:16豎版，產品居中佔畫面60%，頂部1/3留給大號標題文字，底部1/5留給價格/CTA標籤",
                               "prompt": "professional product photography, wireless earbuds centered, warm orange and dark grey color scheme, dramatic studio lighting, 9:16 aspect ratio, high contrast, commercial advertising style, sharp details, 8k quality",
                               "rationale": "抖音用戶0.5秒決定是否停留，暖色+中心構圖+大字標題的組合經A/B測試點擊率最高"}}},
        {"mode": "cover", "platform": "bilibili", "topic": "歷史知識科普",
         "output": {"summary": "B站封面偏好信息密度高+設計感強，左主體右文字的經典佈局配合科技感色調",
                    "tactic": {"scene": "cover", "target_platform": "bilibili",
                               "style": "3D渲染+平面設計混合，電影感色調，信息圖表元素",
                               "color_palette": "深藍紫主調配金色點綴，科技感冷色",
                               "composition": "16:9橫版，左側3/5為視覺主體（3D歷史場景），右側2/5為大字標題+副標題，底部進度條裝飾",
                               "prompt": "cinematic thumbnail, 3D rendered ancient chinese historical scene, deep blue and gold color palette, dramatic lighting with volumetric fog, 16:9 aspect ratio, left space for text overlay, octane render quality, mysterious atmosphere",
                               "rationale": "B站用戶對電影感封面點擊率最高，左圖右文的經典佈局確保文字可讀性"}}},
        {"mode": "social", "platform": "", "topic": "平價護膚品",
         "output": {"summary": "多平台差異化策略：小紅書走精緻平舖+柔和色調，抖音走高對比+大字報風，B站走專業感+信息圖表",
                    "tactic": {"scene": "social_post", "target_platform": "xiaohongshu",
                               "style": "精緻平面設計，柔和光影，平鋪拍攝風格",
                               "color_palette": "奶油白主調配玫瑰粉點綴，柔和粉彩色系",
                               "composition": "3:4豎版，網格佈局展示3-5款產品，留白充足（30%+），品牌logo右下角，整體氛圍溫馨精緻",
                               "prompt": "aesthetic flat lay photography, skincare products arranged on marble surface, cream white and rose pink color palette, soft natural window lighting, 3:4 aspect ratio, clean minimalist composition, xiaohongshu lifestyle style, high-end catalog quality",
                               "rationale": "小紅書用戶對'精緻感'有強烈偏好，平價產品用高端視覺包裝能打破'便宜=low'的認知"}}},
        {"mode": "social", "platform": "", "topic": "職場效率工具",
         "output": {"summary": "工具類內容配圖應突出'效率感'和'專業感'，不同平台需調整專業度 vs 親和力的平衡",
                    "tactic": {"scene": "thumbnail", "target_platform": "zhihu",
                               "style": "極簡信息圖表風，理性藍灰色調，大量留白",
                               "color_palette": "理性藍灰主調配白色背景，少量橙色作為CTA強調色",
                               "composition": "16:9橫版，左文右圖（65:35比例），文字使用無襯線字體，數據用圖表/圖標輔助展示",
                               "prompt": "minimalist infographic design, productivity and efficiency concept, clean blue-grey and white color scheme, geometric icons and simple charts, 16:9 aspect ratio, professional knowledge-sharing aesthetic, plenty of negative space, vector art style",
                               "rationale": "知乎用戶對'知識感'設計有天然信任，極簡風格降低視覺噪音讓信息本身成為主角"}}},
        {"mode": "trend", "platform": "", "topic": "2025視覺趨勢",
         "output": {"summary": "2025年社交媒體視覺趨勢呈現'兩極化'：超現實3D和紀實原生態並行，品牌需同時佈局兩端",
                    "visual_trend": "2025年社交媒體視覺三大趨勢：1) AI超現實主義（Midjourney/Flux生成的超現實畫面成為主流）2) 紀實原生態（手機直出、無濾鏡、生活感）3) 新中式美學（傳統元素用現代設計語言重構）",
                    "tactic": {"scene": "trend", "target_platform": "通用",
                               "style": "AI超現實主義 — 真實與虛構的邊界模糊，夢幻光影+不合理比例+高精細度",
                               "color_palette": "無固定配色，趨勢是'大膽實驗'：霓虹色+自然色並置、單色調+高飽和點綴",
                               "composition": "非對稱構圖成為主流，打破傳統網格系統，隨機性+留白並存",
                               "prompt": "surrealist digital art, dreamlike atmosphere, unexpected scale relationships, neon accent colors against muted natural tones, asymmetrical composition, hyperdetailed, trending on artstation, 2025 aesthetic, AI-generated fine art style",
                               "rationale": "AI工具的普及讓超現實視覺的創作成本歸零，預計2025年將出現大量此類內容"}}},
    ]

    _FEWSHOT_BAD = [
        {"mode": "cover", "platform": "douyin",
         "output": {"style": "好看的風格", "color_palette": "#FF6B35 #FFD700",
                    "prompt": "a nice picture of earphone, good quality, beautiful colors",
                    "rationale": "這樣做比較好看"},
         "why_bad": "❌ 錯誤示範：color_palette 使用 HEX 色號（LLM 會隨機編造不存在的顏色搭配）、prompt 過於簡單（無風格關鍵詞/構圖/畫質描述）、rationale 無平台數據支撐"},
        {"mode": "social", "platform": "",
         "output": {"summary": "不同平台用不同顏色就行",
                    "tactic": {"target_platform": "all", "style": "好看就行", "prompt": "beautiful social media post",
                               "rationale": "大家都喜歡好看的"}},
         "why_bad": "❌ 錯誤示範：無平台差異化（'all'不是策略）、prompt 空泛無法生成可用圖片、無構圖/比例/風格具體描述"},
    ]

    async def _llm_generate(
        self,
        mode: str,
        topic: str,
        platform: str,
        trend_items: list,
        products: list,
    ) -> VisualReport:
        """DeepSeek LLM 智能配圖策略（v2 增強 prompt）。"""
        context_parts = [f"主题: {topic or '通用'}"]
        if platform:
            context_parts.append(f"目标平台: {platform}")

        if trend_items:
            titles = [
                it.get("title", it.title if hasattr(it, "title") else "")[:40]
                for it in trend_items[:5]
            ]
            if titles:
                context_parts.append(f"爆款趋势: {', '.join(titles)}")

        if products:
            names = [
                p.get("name", p.name if hasattr(p, "name") else "")[:30]
                for p in products[:5]
            ]
            if names:
                context_parts.append(f"选品: {', '.join(names)}")

        mode_examples = [ex for ex in self._FEWSHOT_GOOD if ex["mode"] == mode]
        if not mode_examples:
            mode_examples = self._FEWSHOT_GOOD[:3]
        good_examples_text = "\n".join(
            f"  ✅ [{ex['mode']}] {ex.get('platform', '')} {ex.get('topic', '')}\n     {json.dumps(ex['output'], ensure_ascii=False)[:400]}"
            for ex in mode_examples
        )
        bad_examples_text = "\n".join(
            f"  ❌ [{ex['mode']}]\n     {ex['why_bad']}"
            for ex in self._FEWSHOT_BAD
        )

        prompt = f"""你是頂級視覺策略師（PicTactic），精通 Midjourney、Stable Diffusion、DALL-E 等 AI 生圖工具的提示詞編寫，熟悉各社交平台的視覺偏好和設計規範。

## 任務
當前模式: **{mode}**。根據模式為指定主題設計視覺策略方案。

## 品質標準
- 好的方案：AI prompt 具體可用（直接複製到 Midjourney 能出高質量圖）、配色用形容詞而非色號、平台差異化明顯、rationale 有數據或心理學依據
- 差的方案：prompt 過於簡單（如 "a nice picture"）、用 HEX 色號（LLM 會虛構不存在的配色）、所有平台用同一方案、rationale 空泛如「這樣好看」

## ⚠️ color_palette 重要規範
**禁止使用 HEX 色號（如 #FF6B35）！** 因為 LLM 無法準確理解顏色數值，會隨機編造。必須改用色彩形容詞描述，例如：
- ✅ 正確：「暖橙色主調搭配深灰背景，高飽和暖色衝擊」
- ✅ 正確：「奶油白主調配玫瑰粉點綴，柔和粉彩色系」
- ✅ 正確：「深藍紫主調配金色點綴，科技感冷色」
- ❌ 錯誤：「#FF6B35 #FFD700 #00CEC9」（無意義的數字組合）

## AI Prompt 規範
- 必須使用 **英文**（Midjourney/SD 對英文理解最佳）
- 必須包含：主體描述 + 風格關鍵詞 + 構圖比例 + 光影描述 + 畫質關鍵詞
- 推薦後綴關鍵詞：8k quality, professional, high detail, trending on artstation

## Few-Shot 正例（{mode} 模式專屬）
{good_examples_text}

## Few-Shot 負例（避免以下錯誤）
{bad_examples_text}

## 邊界情況處理
- 無趨勢/選品數據：基於主題和平台獨立設計，標註「獨立創作模式」
- cover 模式未指定平台：預設為 douyin（因抖音封面需求最通用）
- trend 模式：至少引用 2 個具體的設計趨勢來源或案例

## 背景數據
{chr(10).join(context_parts)}"""

        try:
            output = await self._call_llm_with_critic(prompt, PicTacticOutput, "pic_tactic", temperature=0.7, max_tokens=4000)

            tactics = [
                VisualTactic(
                    scene=t.scene,
                    target_platform=t.target_platform,
                    style=t.style,
                    color_palette=t.color_palette,
                    composition=t.composition,
                    prompt=t.prompt,
                    rationale=t.rationale,
                )
                for t in output.tactics
            ]

            return VisualReport(
                topic=topic or "通用",
                mode=mode,
                platform=platform,
                total_tactics=len(tactics),
                tactics=tactics,
                visual_trend=output.visual_trend,
                summary=output.summary,
            )
        except Exception as exc:
            logger.warning(f"PicTactic LLM 失败: {exc}")
            return self._fallback(mode, topic, platform, trend_items, products)

    def _fallback(
        self,
        mode: str,
        topic: str,
        platform: str,
        trend_items: list = None,
        products: list = None,
    ) -> VisualReport:
        if mode == "cover" and platform in _PLATFORM_DEFAULTS:
            t = dict(_PLATFORM_DEFAULTS[platform], target_platform=platform)
            return VisualReport(
                topic=topic or "通用",
                mode="cover",
                platform=platform,
                total_tactics=1,
                tactics=[VisualTactic(**t)],
                summary=f"{platform} 封面模板（LLM 不可用）",
            )

        if mode == "social":
            tactics = []
            for p, t in _PLATFORM_DEFAULTS.items():
                if platform and p != platform:
                    continue
                td = dict(t, target_platform=p)
                tactics.append(VisualTactic(**td))
            if not tactics:
                td = dict(_PLATFORM_DEFAULTS["douyin"], target_platform="douyin")
                tactics = [VisualTactic(**td)]
            return VisualReport(
                topic=topic or "通用",
                mode="social",
                platform=platform,
                total_tactics=len(tactics),
                tactics=tactics,
                summary=f"基于 {len(tactics)} 个平台的模板配图策略（LLM 不可用）",
            )

        if mode == "trend":
            tactic = VisualTactic(
                scene="trend",
                target_platform="通用",
                style="mixed",
                color_palette="取决于具体赛道",
                composition="取决于平台规范",
                prompt="trending visual style, contemporary design, 2025 aesthetic",
                rationale="基于文本推断的通用趋势（需 LLM 深度分析）",
            )
            return VisualReport(
                topic=topic or "通用",
                mode="trend",
                total_tactics=1,
                tactics=[tactic],
                visual_trend=_TREND_DEFAULT,
                summary="视觉趋势模板（LLM 不可用）",
            )

        return VisualReport(topic=topic or "通用", mode=mode, summary="未知模式")
