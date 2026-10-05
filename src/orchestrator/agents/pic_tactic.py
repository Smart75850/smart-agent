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
        {"mode": "cover", "platform": "douyin", "topic": "蓝牙耳机评测",
         "output": {"summary": "抖音封面核心是高视觉冲击力+大字标题，暖色系+中心构图是点击率最高的组合",
                    "tactic": {"scene": "cover", "target_platform": "douyin",
                               "style": "商业摄影风，高对比度高饱和，产品置于视觉中心",
                               "color_palette": "暖橙色主调搭配深灰背景，高饱和暖色冲击",
                               "composition": "9:16竖版，产品居中占画面60%，顶部1/3留给大号标题文字，底部1/5留给价格/CTA标签",
                               "prompt": "professional product photography, wireless earbuds centered, warm orange and dark grey color scheme, dramatic studio lighting, 9:16 aspect ratio, high contrast, commercial advertising style, sharp details, 8k quality",
                               "rationale": "抖音用户0.5秒决定是否停留，暖色+中心构图+大字标题的组合经A/B测试点击率最高"}}},
        {"mode": "cover", "platform": "bilibili", "topic": "历史知识科普",
         "output": {"summary": "B站封面偏好信息密度高+设计感强，左主体右文字的经典布局配合科技感色调",
                    "tactic": {"scene": "cover", "target_platform": "bilibili",
                               "style": "3D渲染+平面设计混合，电影感色调，信息图表元素",
                               "color_palette": "深蓝紫主调配金色点缀，科技感冷色",
                               "composition": "16:9横版，左侧3/5为视觉主体（3D历史场景），右侧2/5为大字标题+副标题，底部进度条装饰",
                               "prompt": "cinematic thumbnail, 3D rendered ancient chinese historical scene, deep blue and gold color palette, dramatic lighting with volumetric fog, 16:9 aspect ratio, left space for text overlay, octane render quality, mysterious atmosphere",
                               "rationale": "B站用户对电影感封面点击率最高，左图右文的经典布局确保文字可读性"}}},
        {"mode": "social", "platform": "", "topic": "平价护肤品",
         "output": {"summary": "多平台差异化策略：小红书走精致平铺+柔和色调，抖音走高对比+大字报风，B站走专业感+信息图表",
                    "tactic": {"scene": "social_post", "target_platform": "xiaohongshu",
                               "style": "精致平面设计，柔和光影，平铺拍摄风格",
                               "color_palette": "奶油白主调配玫瑰粉点缀，柔和粉彩色系",
                               "composition": "3:4竖版，网格布局展示3-5款产品，留白充足（30%+），品牌logo右下角，整体氛围温馨精致",
                               "prompt": "aesthetic flat lay photography, skincare products arranged on marble surface, cream white and rose pink color palette, soft natural window lighting, 3:4 aspect ratio, clean minimalist composition, xiaohongshu lifestyle style, high-end catalog quality",
                               "rationale": "小红书用户对'精致感'有强烈偏好，平价产品用高端视觉包装能打破'便宜=low'的认知"}}},
        {"mode": "social", "platform": "", "topic": "职场效率工具",
         "output": {"summary": "工具类内容配图应突出'效率感'和'专业感'，不同平台需调整专业度 vs 亲和力的平衡",
                    "tactic": {"scene": "thumbnail", "target_platform": "zhihu",
                               "style": "极简信息图表风，理性蓝灰色调，大量留白",
                               "color_palette": "理性蓝灰主调配白色背景，少量橙色作为CTA强调色",
                               "composition": "16:9横版，左文右图（65:35比例），文字使用无衬线字体，数据用图表/图标辅助展示",
                               "prompt": "minimalist infographic design, productivity and efficiency concept, clean blue-grey and white color scheme, geometric icons and simple charts, 16:9 aspect ratio, professional knowledge-sharing aesthetic, plenty of negative space, vector art style",
                               "rationale": "知乎用户对'知识感'设计有天然信任，极简风格降低视觉噪音让信息本身成为主角"}}},
        {"mode": "trend", "platform": "", "topic": "2025视觉趋势",
         "output": {"summary": "2025年社交媒体视觉趋势呈现'两极化'：超现实3D和纪实原生态并行，品牌需同时布局两端",
                    "visual_trend": "2025年社交媒体视觉三大趋势：1) AI超现实主义（Midjourney/Flux生成的超现实画面成为主流）2) 纪实原生态（手机直出、无滤镜、生活感）3) 新中式美学（传统元素用现代设计语言重构）",
                    "tactic": {"scene": "trend", "target_platform": "通用",
                               "style": "AI超现实主义 — 真实与虚构的边界模糊，梦幻光影+不合理比例+高精细度",
                               "color_palette": "无固定配色，趋势是'大胆实验'：霓虹色+自然色并置、单色调+高饱和点缀",
                               "composition": "非对称构图成为主流，打破传统网格系统，随机性+留白并存",
                               "prompt": "surrealist digital art, dreamlike atmosphere, unexpected scale relationships, neon accent colors against muted natural tones, asymmetrical composition, hyperdetailed, trending on artstation, 2025 aesthetic, AI-generated fine art style",
                               "rationale": "AI工具的普及让超现实视觉的创作成本归零，预计2025年将出现大量此类内容"}}},
    ]

    _FEWSHOT_BAD = [
        {"mode": "cover", "platform": "douyin",
         "output": {"style": "好看的风格", "color_palette": "#FF6B35 #FFD700",
                    "prompt": "a nice picture of earphone, good quality, beautiful colors",
                    "rationale": "这样做比较好看"},
         "why_bad": "❌ 错误示范：color_palette 使用 HEX 色号（LLM 会随机编造不存在的颜色搭配）、prompt 过于简单（无风格关键词/构图/画质描述）、rationale 无平台数据支撑"},
        {"mode": "social", "platform": "",
         "output": {"summary": "不同平台用不同颜色就行",
                    "tactic": {"target_platform": "all", "style": "好看就行", "prompt": "beautiful social media post",
                               "rationale": "大家都喜欢好看的"}},
         "why_bad": "❌ 错误示范：无平台差异化（'all'不是策略）、prompt 空泛无法生成可用图片、无构图/比例/风格具体描述"},
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

        prompt = f"""<role>
你是视觉策略师（PicTactic）。你的唯一职责：Design 各平台配图方案，Compose AI 生图提示词（英文），Select 配色与构图策略。
</role>

<scope>
OWN: 视觉风格设计、AI prompt 编写、配色方案、构图策略、平台差异化
BOUNDARY: 不生成文案（CopyWriter）、不分析数据（ContentRemixer）、不评估内容（TrendScout）
</scope>

<quality_standards>
专业级输出必须满足：
1. prompt 英文 + 主体描述 + 风格关键词 + 构图比例 + 光影 + 画质后缀（8k, professional）
2. color_palette 用色彩形容词（「暖橙主调配深灰背景」），禁止 HEX 色号
3. composition 含比例+元素布局+文字位置（30字以上）
4. rationale 结合平台用户偏好+点击率数据
5. 每个平台方案必须有差异化
</quality_standards>

<mode>{mode}</mode>

## ⚠️ color_palette 重要规范
**禁止使用 HEX 色号（如 #FF6B35）！** 因为 LLM 无法准确理解颜色数值，会随机编造。必须改用色彩形容词描述，例如：
- ✅ 正确：「暖橙色主调搭配深灰背景，高饱和暖色冲击」
- ✅ 正确：「奶油白主调配玫瑰粉点缀，柔和粉彩色系」
- ✅ 正确：「深蓝紫主调配金色点缀，科技感冷色」
- ❌ 错误：「#FF6B35 #FFD700 #00CEC9」（无意义的数字组合）

## AI Prompt 规范
- 必须使用 **英文**（Midjourney/SD 对英文理解最佳）
- 必须包含：主体描述 + 风格关键词 + 构图比例 + 光影描述 + 画质关键词
- 推荐后缀关键词：8k quality, professional, high detail, trending on artstation

## Few-Shot 正例（{mode} 模式专属）
{good_examples_text}

## Few-Shot 负例（避免以下错误）
{bad_examples_text}

## 边界情况处理
- 无趋势/选品数据：基于主题和平台独立设计，标注「独立创作模式」
- cover 模式未指定平台：预设为 douyin（因抖音封面需求最通用）
- trend 模式：至少引用 2 个具体的设计趋势来源或案例

## 背景数据
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
