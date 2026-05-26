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

from src.orchestrator.agents.base import BaseAgent
from src.utils.logger import logger

# ── 平台降级模板 ──────────────────────────────────────────────

_PLATFORM_DEFAULTS = {
    "douyin": {
        "scene": "cover",
        "style": "photography",
        "color_palette": "高饱和暖色 #FF6B35 #FFD700",
        "composition": "中心构图，大字标题占顶部1/3",
        "prompt": "eye-catching product photo, vibrant colors, trending on douyin, 9:16 aspect ratio, high contrast",
        "rationale": "抖音用户偏好高视觉冲击力封面",
    },
    "xiaohongshu": {
        "scene": "social_post",
        "style": "flat_illustration",
        "color_palette": "柔和粉彩 #F8E8E0 #D4A5A5",
        "composition": "网格布局，3:4 竖版，留白充足",
        "prompt": "aesthetic flat lay, soft pastel colors, xiaohongshu style, clean composition, 3:4 aspect ratio, natural lighting",
        "rationale": "小红书偏好精致、有质感的视觉风格",
    },
    "bilibili": {
        "scene": "cover",
        "style": "3d_render",
        "color_palette": "科技蓝紫 #6C5CE7 #00CEC9",
        "composition": "16:9 横版，左侧主体右侧文字",
        "prompt": "cinematic thumbnail, bold contrast, bilibili tech style, 16:9 aspect ratio, dramatic lighting, cyberpunk elements",
        "rationale": "B站用户偏好信息密度高、设计感强的封面",
    },
    "zhihu": {
        "scene": "banner",
        "style": "minimalist",
        "color_palette": "理性蓝灰 #2C3E50 #BDC3C7",
        "composition": "16:9 横版，左文右图，信息图表风",
        "prompt": "minimalist infographic style, clean typography, knowledge-sharing aesthetic, 16:9, muted blue tones, professional",
        "rationale": "知乎偏好理性、知识感的设计风格",
    },
    "kuaishou": {
        "scene": "cover",
        "style": "photography",
        "color_palette": "暖色高饱和 #FF5722 #FFC107",
        "composition": "9:16 竖版，人物居中，标题底部",
        "prompt": "bold and authentic, street style photography, kuaishou vibe, 9:16, warm tones, relatable",
        "rationale": "快手偏好真实感、接地气的视觉风格",
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

    async def _llm_generate(
        self,
        mode: str,
        topic: str,
        platform: str,
        trend_items: list,
        products: list,
    ) -> VisualReport:
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

        mode_prompts = {
            "cover": (
                f'{{"summary": "封面策略一句话", '
                f'"tactics": [{{"scene": "cover", "target_platform": "{platform or "douyin"}", '
                f'"style": "视觉风格", "color_palette": "配色方案+色号", '
                f'"composition": "构图描述", '
                f'"prompt": "英文AI生图提示词(Midjourney/Stable Diffusion通用)", '
                f'"rationale": "推荐理由"}}]}}'
            ),
            "social": (
                f'{{"summary": "多平台配图策略一句话", '
                f'"tactics": [{{"scene": "cover/social_post/thumbnail", '
                f'"target_platform": "douyin/xiaohongshu/bilibili/zhihu/kuaishou", '
                f'"style": "视觉风格", "color_palette": "配色方案+色号", '
                f'"composition": "构图描述", '
                f'"prompt": "英文AI生图提示词", '
                f'"rationale": "推荐理由"}}]}}'
            ),
            "trend": (
                f'{{"summary": "视觉趋势一句话", "visual_trend": "当前流行视觉风格趋势描述", '
                f'"tactics": [{{"scene": "trend", "target_platform": "通用", '
                f'"style": "趋势风格", "color_palette": "趋势配色", '
                f'"composition": "趋势构图", '
                f'"prompt": "趋势风格AI提示词示例", '
                f'"rationale": "趋势理由"}}]}}'
            ),
        }

        prompt = (
            f"你是一个视觉策略专家。模式: {mode}。\n"
            f"你精通 Midjourney、Stable Diffusion、DALL-E 等 AI 生图工具的提示词编写。\n"
            f"你了解抖音/小红书/B站/知乎/快手等平台的视觉偏好和设计规范。\n\n"
            + "\n".join(context_parts)
            + f"\n\n请返回 JSON（不要 markdown 代码块）：\n"
            + mode_prompts.get(mode, mode_prompts["social"])
        )

        try:
            content = await self._call_llm(prompt, temperature=0.7)
            parsed = self._parse_json(content)

            tactics = [
                VisualTactic(
                    scene=t.get("scene", ""),
                    target_platform=t.get("target_platform", ""),
                    style=t.get("style", ""),
                    color_palette=t.get("color_palette", ""),
                    composition=t.get("composition", ""),
                    prompt=t.get("prompt", ""),
                    rationale=t.get("rationale", ""),
                )
                for t in parsed.get("tactics", [])
            ]

            return VisualReport(
                topic=topic or "通用",
                mode=mode,
                platform=platform,
                total_tactics=len(tactics),
                tactics=tactics,
                visual_trend=parsed.get("visual_trend", ""),
                summary=parsed.get("summary", ""),
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
