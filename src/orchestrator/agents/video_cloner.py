"""VideoCloneAgent — 视频克隆引擎。

下载视频 → 智能抽帧 → QWEN-VL 视觉分析 → DeepSeek 生成复刻方案。

用法:
    agent = VideoCloneAgent()
    report = await agent.run("https://www.douyin.com/video/7123456789", platform="douyin")
"""

import asyncio
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from config.settings import settings
from src.orchestrator.agents.base import BaseAgent
from src.utils.logger import logger

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DOWNLOAD_DIR = Path(settings.DOWNLOAD_DIR or str(_PROJECT_ROOT / "downloads"))


# ── Pydantic 输出模型 ─────────────────────────────────────────

class StyleAnalysisOutput(BaseModel):
    color_scheme: str = Field(min_length=15, description="主色调+辅色描述")
    lighting_style: str = Field(min_length=10, description="光线风格")
    composition_pattern: str = Field(min_length=15, description="构图模式")
    text_overlay_style: str = Field(min_length=12, description="字幕/花字风格")
    transition_style: str = Field(min_length=10, description="转场风格")
    color_grading: str = Field(min_length=15, description="调色倾向")
    pace_description: str = Field(min_length=20, description="节奏描述")
    objects_and_scenes: str = Field(min_length=15, description="画面中的关键物体/场景元素")
    overall_vibe: str = Field(min_length=15, description="3-5个形容词总结视觉氛围")


class CanvaKeywordsOutput(BaseModel):
    cn_keywords: list[str] = Field(min_length=3, max_length=8, description="中文Canva搜索关键词")
    en_keywords: list[str] = Field(min_length=3, max_length=8, description="英文Canva搜索关键词")
    jianying_keywords: list[str] = Field(min_length=3, max_length=8, description="剪映搜索关键词")


class BGMTrack(BaseModel):
    genre: Literal["电子", "流行", "国风", "爵士", "摇滚", "嘻哈", "氛围", "古典", "轻音乐"]
    bpm_range: str = Field(description="BPM范围，如'90-110'")
    mood: str = Field(min_length=8, description="情绪氛围")
    search_keyword: str = Field(min_length=6, description="搜索关键词")


class ShotInstruction(BaseModel):
    shot_number: int = Field(description="镜头序号")
    duration_seconds: int = Field(description="建议时长（秒）")
    camera_angle: str = Field(description="机位/角度")
    action_description: str = Field(min_length=15, description="画面内容详述")
    text_overlay: str = Field(default="", description="画面文字")
    voiceover_hint: str = Field(default="", description="配音提示")
    transition_to_next: str = Field(default="硬切", description="转场方式")


class VideoCloneOutput(BaseModel):
    style_analysis: StyleAnalysisOutput
    canva_keywords: CanvaKeywordsOutput
    rewritten_copy: str = Field(min_length=40, description="改写后文案")
    bgm_recommendations: list[BGMTrack] = Field(min_length=1, max_length=5)
    shooting_script: list[ShotInstruction] = Field(min_length=3, max_length=20)
    summary: str = Field(min_length=40, description="克隆方案总结")


# ── Dataclass DTO ─────────────────────────────────────────────

@dataclass
class ShotInstructionDTO:
    shot_number: int = 0
    duration_seconds: int = 3
    camera_angle: str = ""
    action_description: str = ""
    text_overlay: str = ""
    voiceover_hint: str = ""
    transition_to_next: str = "硬切"


@dataclass
class CloneReport:
    platform: str = ""
    video_url: str = ""
    video_title: str = ""
    duration_seconds: float = 0.0
    total_frames_analyzed: int = 0
    color_scheme: str = ""
    lighting_style: str = ""
    composition_pattern: str = ""
    text_overlay_style: str = ""
    transition_style: str = ""
    color_grading: str = ""
    pace_description: str = ""
    objects_and_scenes: str = ""
    overall_vibe: str = ""
    canva_cn_keywords: list[str] = field(default_factory=list)
    canva_en_keywords: list[str] = field(default_factory=list)
    jianying_keywords: list[str] = field(default_factory=list)
    rewritten_copy: str = ""
    bgm_recommendations: list[dict] = field(default_factory=list)
    shooting_script: list[ShotInstructionDTO] = field(default_factory=list)
    summary: str = ""
    errors: list[str] = field(default_factory=list)


# ── 平台 URL 识别 ─────────────────────────────────────────────

_PLATFORM_URL_MAP = {
    "douyin.com": "douyin",
    "bilibili.com": "bilibili",
    "xiaohongshu.com": "xiaohongshu",
    "xhslink.com": "xiaohongshu",
    "kuaishou.com": "kuaishou",
    "zhihu.com": "zhihu",
}


def detect_platform(url: str) -> str:
    for domain, plat in _PLATFORM_URL_MAP.items():
        if domain in url:
            return plat
    return "unknown"


# ── Agent ─────────────────────────────────────────────────────

class VideoCloneAgent(BaseAgent):
    """视频克隆引擎。"""

    def __init__(self):
        super().__init__()

    # ── 主入口 ──────────────────────────────────────────────

    async def run(
        self,
        video_url: str,
        platform: str = "",
        max_frames: int = 30,
    ) -> CloneReport:
        platform = platform or detect_platform(video_url)
        report = CloneReport(platform=platform, video_url=video_url)

        if platform == "unknown":
            report.errors.append(f"无法识别平台: {video_url}")
            return report

        try:
            # Step 1: 下载
            video = await self._step_download(video_url, platform)
            report.video_title = video.title
            report.duration_seconds = video.duration_seconds

            # Step 2: 抽帧
            frames = await self._step_extract_frames(video, max_frames)
            report.total_frames_analyzed = len(frames)
            if not frames:
                report.errors.append("抽帧失败，无可用帧")
                return report

            # Step 3: QWEN-VL 视觉分析
            qwen_output = await self._step_analyze_style(frames, video.title)
            report.color_scheme = qwen_output.color_scheme
            report.lighting_style = qwen_output.lighting_style
            report.composition_pattern = qwen_output.composition_pattern
            report.text_overlay_style = qwen_output.text_overlay_style
            report.transition_style = qwen_output.transition_style
            report.color_grading = qwen_output.color_grading
            report.pace_description = qwen_output.pace_description
            report.objects_and_scenes = qwen_output.objects_and_scenes
            report.overall_vibe = qwen_output.overall_vibe

            # Step 4: DeepSeek 生成克隆方案
            clone_output = await self._step_generate_plan(
                qwen_output, video.title, platform, video.duration_seconds
            )
            report.canva_cn_keywords = clone_output.canva_keywords.cn_keywords
            report.canva_en_keywords = clone_output.canva_keywords.en_keywords
            report.jianying_keywords = clone_output.canva_keywords.jianying_keywords
            report.rewritten_copy = clone_output.rewritten_copy
            report.bgm_recommendations = [m.model_dump() for m in clone_output.bgm_recommendations]
            report.shooting_script = [
                ShotInstructionDTO(
                    shot_number=s.shot_number,
                    duration_seconds=s.duration_seconds,
                    camera_angle=s.camera_angle,
                    action_description=s.action_description,
                    text_overlay=s.text_overlay,
                    voiceover_hint=s.voiceover_hint,
                    transition_to_next=s.transition_to_next,
                )
                for s in clone_output.shooting_script
            ]
            report.summary = clone_output.summary

        except Exception as exc:
            logger.error(f"VideoCloneAgent 失败: {exc}")
            report.errors.append(str(exc))

        return report

    async def as_node(self, state: dict) -> dict:
        url = state.get("video_url", "")
        plat = state.get("platform", "")
        if not url:
            return {"clone_report": None}
        report = await self.run(url, platform=plat)
        return {"clone_report": asdict(report)}

    # ── Step 1: 下载视频 ────────────────────────────────────

    async def _step_download(self, video_url: str, platform: str):
        from src.downloader.media_downloader import MediaExtractor, MediaDownloader

        item = {"link": video_url, "aweme_id": video_url.rsplit("/", 1)[-1].split("?")[0]}
        item.setdefault("cover_url", "")

        extractor = MediaExtractor()
        video_src = await extractor.extract_video(platform, item)
        if not video_src:
            raise RuntimeError(f"无法提取视频 URL: {video_url}")

        out_dir = str(_DOWNLOAD_DIR / "clone_videos")
        os.makedirs(out_dir, exist_ok=True)

        dl = MediaDownloader()
        try:
            results = await dl.download_urls(
                urls=[video_src],
                output_dir=out_dir,
                filenames=[f"{platform}_{int(time.time())}.mp4"],
            )
        finally:
            await dl.close()

        if not results or results[0].status not in ("success", "skipped"):
            raise RuntimeError(f"下载失败: {results[0].error if results else '未知'}")

        filepath = results[0].filepath

        # 获取时长
        try:
            from src.utils.ffmpeg_utils import probe_duration
            duration = await probe_duration(filepath)
        except Exception:
            duration = 0.0

        downloaded = DownloadedVideo(
            platform=platform,
            video_id=item["aweme_id"],
            filepath=filepath,
            title="",
            duration_seconds=duration,
        )
        return downloaded

    # ── Step 2: 抽帧 ────────────────────────────────────────

    async def _step_extract_frames(self, video, max_frames: int = 30):
        from src.utils.ffmpeg_utils import extract_keyframes_smart, extract_keyframes_uniform

        ts = int(time.time() * 1000)
        out_dir = str(_DOWNLOAD_DIR / "clone_frames" / f"{video.video_id}_{ts}")
        os.makedirs(out_dir, exist_ok=True)

        logger.info(f"抽帧: {video.filepath} -> {out_dir}")

        try:
            paths = await extract_keyframes_smart(
                video.filepath, out_dir,
                duration_seconds=video.duration_seconds,
                max_frames=max_frames,
            )
        except Exception:
            paths = []

        if not paths:
            logger.info("场景检测抽帧失败，使用均匀抽帧")
            paths = await extract_keyframes_uniform(
                video.filepath, out_dir,
                duration_seconds=video.duration_seconds,
                max_frames=max_frames,
            )

        frames = [
            FrameInfo(i, 0.0, p)
            for i, p in enumerate(paths)
        ]
        return frames[:max_frames]

    # ── Step 3: QWEN-VL 视觉分析 ────────────────────────────

    async def _step_analyze_style(self, frames, title: str):
        if not self._qwen_api_key:
            logger.warning("QWEN_API_KEY 未配置，使用文本回退")
            return self._qwen_fallback(title)

        image_paths = [f.filepath for f in frames]
        total = len(image_paths)

        prompt = f"""<role>
你是视频视觉风格分析师。你的唯一职责：Observe 关键帧画面，Describe 视觉元素，Identify 风格模式。
</role>

<scope>
OWN: 逐帧观察并描述视觉元素、识别颜色/光线/构图/文字/转场模式
BOUNDARY: 不评价视频内容好坏、不推荐改进方案、不生成文案
ESCALATE: 图片质量太差 → 标注 uncertainty；纯文字帧 → 单独标注
</scope>

<task>
观察以下从该视频中提取的 {total} 张关键帧截图（按时间顺序排列）。
视频标题：{title}
逐帧分析并总结该视频的视觉风格。
</task>

<output_format>
返回纯JSON：
{{{{
  "color_scheme": "主色调+辅色描述（30字以上）",
  "lighting_style": "光线风格描述（20字以上）",
  "composition_pattern": "构图模式描述（30字以上）",
  "text_overlay_style": "字幕/文字风格，位置+字体+动画（30字以上）",
  "transition_style": "转场风格描述（20字以上）",
  "color_grading": "调色倾向（30字以上）",
  "pace_description": "节奏描述，含快慢变化点（30字以上）",
  "objects_and_scenes": "画面关键物体+场景元素（30字以上）",
  "overall_vibe": "3-5个形容词总结视觉氛围（20字以上）"
}}}}
</output_format>"""

        try:
            content = await self._call_qwen_vl(prompt, image_paths, temperature=0.3, max_tokens=2000)
            parsed = self._parse_json(content)
            return StyleAnalysisOutput(**parsed)
        except Exception as exc:
            logger.warning(f"QWEN-VL 分析失败，使用回退: {exc}")
            return self._qwen_fallback(title)

    def _qwen_fallback(self, title: str) -> StyleAnalysisOutput:
        return StyleAnalysisOutput(
            color_scheme=f"基于标题'{title[:30]}'推断：需安装 QWEN_API_KEY 获取精准分析",
            lighting_style="（需 QWEN-VL）",
            composition_pattern="（需 QWEN-VL）",
            text_overlay_style="（需 QWEN-VL）",
            transition_style="（需 QWEN-VL）",
            color_grading="（需 QWEN-VL）",
            pace_description="（需 QWEN-VL）",
            objects_and_scenes="（需 QWEN-VL）",
            overall_vibe="（需 QWEN-VL）",
        )

    # ── Step 4: DeepSeek 生成克隆方案 ────────────────────────

    async def _step_generate_plan(
        self,
        style: StyleAnalysisOutput,
        title: str,
        platform: str,
        duration: float,
    ):
        prompt = f"""<role>
你是视频复刻方案策划师。你的唯一职责：Based on 视觉风格分析，Generate 可执行的复刻方案。
</role>

<scope>
OWN: 生成Canva/剪映搜索关键词、改写文案、BGM推荐、分镜脚本
BOUNDARY: 不修改原视频风格方向、不生成与原文案高度相似的内容（查重率<15%）
</scope>

<context>
## 原视频
- 标题：{title}
- 平台：{platform}
- 时长：约 {duration:.0f} 秒

## QWEN-VL 视觉风格分析
- 配色：{style.color_scheme}
- 光线：{style.lighting_style}
- 构图：{style.composition_pattern}
- 文字风格：{style.text_overlay_style}
- 转场：{style.transition_style}
- 调色：{style.color_grading}
- 节奏：{style.pace_description}
- 画面元素：{style.objects_and_scenes}
- 整体氛围：{style.overall_vibe}
</context>

<quality_standards>
1. Canva关键词必须精确（含中英文），能在Canva直接搜到相似风格模板
2. 剪映关键词针对剪映模板库优化
3. 改写文案查重率<15%，保留核心信息点但改变句式/用词/顺序
4. BGM推荐至少3首，每首含曲风+BPM范围+情绪+搜索关键词
5. 分镜脚本可执行，含具体时长+机位+画面+文字+转场
</quality_standards>

<task>
基于以上视觉风格分析，为该视频生成一套完整的复刻方案。
</task>

<output_format>
返回纯JSON：
{{{{"style_analysis": ...,
 "canva_keywords": {{{{"cn_keywords": ["关键词1","关键词2",...],
   "en_keywords": ["keyword1","keyword2",...],
   "jianying_keywords": ["剪映关键词1","剪映关键词2",...]}}}},
 "rewritten_copy": "改写后的完整文案（200字以上）",
 "bgm_recommendations": [{{{{"genre":"电子","bpm_range":"110-130","mood":"科技感 快节奏","search_keyword": "科技背景音乐 快节奏"}}}}, ...],
 "shooting_script": [{{{{"shot_number":1,"duration_seconds":8,"camera_angle":"特写","action_description":"产品慢慢靠近镜头","text_overlay":"这东西太好用了","voiceover_hint":"这东西太好用了...","transition_to_next":"淡入"}}}}, ...],
 "summary": "50字以上总结，含总体风格方向+适用场景"
}}}}
</output_format>"""

        try:
            output = await self._call_llm_with_critic(
                prompt, VideoCloneOutput, "video_cloner", temperature=0.3, max_tokens=4000
            )
            return output
        except Exception as exc:
            logger.warning(f"DeepSeek 生成失败: {exc}")
            return self._clone_fallback(style, platform)

    def _clone_fallback(self, style: StyleAnalysisOutput, platform: str) -> VideoCloneOutput:
        return VideoCloneOutput(
            style_analysis=style,
            canva_keywords=CanvaKeywordsOutput(
                cn_keywords=["科技产品介绍", "数码测评", "工具展示"],
                en_keywords=["tech review", "product demo"],
                jianying_keywords=["科技测评", "数码介绍"],
            ),
            rewritten_copy="（需 DeepSeek API Key 生成改写文案）",
            bgm_recommendations=[BGMTrack(genre="电子", bpm_range="110-130", mood="科技感", search_keyword="科技背景音乐")],
            shooting_script=[ShotInstruction(shot_number=1, duration_seconds=8, camera_angle="中景", action_description="产品展示")],
            summary="（降级模式，需 API Key 获取完整方案）",
        )


# ── Helper dataclasses ────────────────────────────────────────

@dataclass
class FrameInfo:
    frame_index: int
    timestamp_seconds: float
    filepath: str


@dataclass
class DownloadedVideo:
    platform: str
    video_id: str
    filepath: str
    title: str = ""
    duration_seconds: float = 0.0
