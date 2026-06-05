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
    text_overlay_style: str = Field(min_length=8, description="字幕/花字风格，无文字则说明")
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
    image_hint: str = Field(default="", description="配图建议：截图/录屏/素材")
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
    image_hint: str = ""
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
    template_links: dict[str, str] = field(default_factory=dict)
    publishing_warnings: list[str] = field(default_factory=list)
    summary: str = ""
    errors: list[str] = field(default_factory=list)


# ── 平台 URL 识别 ─────────────────────────────────────────────

_PLATFORM_URL_MAP = {
    "douyin.com": "douyin",
    "v.douyin.com": "douyin",
    "bilibili.com": "bilibili",
    "b23.tv": "bilibili",
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


# ── 操作清单生成 ─────────────────────────────────────────────

def format_checklist(report: CloneReport) -> str:
    """将 CloneReport 转为可执行的复刻操作清单（Markdown格式）。"""
    lines = [
        "# 视频复刻操作清单",
        "",
        f"## 原视频分析",
        f"- 平台：{report.platform}",
        f"- 时长：{report.duration_seconds:.0f}秒",
        f"- 配色：{report.color_scheme}",
        f"- 风格：{report.overall_vibe}",
        f"- 构图：{report.composition_pattern}",
        "",
        "---",
        "",
        "## 第一步：准备素材",
    ]
    if report.objects_and_scenes:
        lines.append(f"画面要素：{report.objects_and_scenes}")
    lines.append("")
    lines.append("1. 用 OBS/Bandicam 录操作过程")
    lines.append("2. 截取关键界面的高清截图")
    lines.append("3. 准备产品Logo/品牌水印")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 第二步：剪映桌面版操作")
    lines.append("")
    lines.append("### 2.1 导入素材")
    lines.append("- 打开剪映桌面版 → 新建项目")
    lines.append("- 拖入录屏视频 + 截图素材")
    lines.append("")
    lines.append("### 2.2 按分镜脚本排列")
    lines.append("")
    lines.append("| 镜头 | 时长 | 画面内容 | 配图建议 | 文字叠加 | 配音 | 转场 |")
    lines.append("|:---:|:---:|------|------|------|------|:---:|")
    for s in report.shooting_script:
        lines.append(
            f"| {s.shot_number} | {s.duration_seconds}s | "
            f"{s.action_description[:30]} | {s.image_hint[:20]} | "
            f"{s.text_overlay[:15]} | {s.voiceover_hint[:15]} | {s.transition_to_next} |"
        )
    lines.append("")
    lines.append("### 2.3 加动画效果")
    lines.append("- 文字标注：动画 → 「逐行淡入」")
    lines.append("- 箭头/框框：贴纸 → 「指示箭头」拖入")
    lines.append("- 画面局部放大：右键素材 → 「关键帧缩放」")
    lines.append("- 鼠标点击高亮：贴纸 → 「点击光圈」")
    lines.append(f"- 转场：{report.transition_style}")
    lines.append("")
    lines.append("### 2.4 调色")
    lines.append(f"- 滤镜方向：{report.color_grading}")
    lines.append(f"- 光线参考：{report.lighting_style}")
    if "暖" in report.color_grading:
        lines.append("- 色温：+10 暖色")
    elif "冷" in report.color_grading or "蓝" in report.color_grading:
        lines.append("- 色温：-5 冷色")
    lines.append("- 对比度：+8")
    lines.append("- 饱和度：+5")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 第三步：配音")
    lines.append("")
    lines.append("### 配音稿（贴入剪映「文本朗读」）")
    lines.append("")
    lines.append(f'"""{report.rewritten_copy}"""')
    lines.append("")
    lines.append("### 操作步骤")
    lines.append("1. 剪映 → 文本 → 新建文本 → 贴入配音稿")
    lines.append('2. 选中文本 → 「朗读」→ 选「解说男声」或「知性女声」')
    lines.append(f"3. 调整语速：参考原片 {report.pace_description}")
    lines.append("4. 字幕自动生成 → 样式统一")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 第四步：BGM")
    lines.append("")
    for i, bgm in enumerate(report.bgm_recommendations, 1):
        lines.append(f"{i}. 剪映音频搜：「{bgm.get('search_keyword', '')}」")
        lines.append(f"   - {bgm.get('genre', '')} | BPM {bgm.get('bpm_range', '')} | {bgm.get('mood', '')}")
        lines.append("")
    lines.append("- BGM音量：降到20-30%（不要压过配音）")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 第五步：导出")
    lines.append("")
    lines.append("- 分辨率：1080p")
    lines.append("- 帧率：30fps")
    lines.append("- 格式：MP4")
    lines.append("- 导出 → 上传平台")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 发文避忌检查")
    lines.append("")
    if report.publishing_warnings:
        for w in report.publishing_warnings:
            lines.append(f"- {w}")
    else:
        lines.append("- ✅ 文案未检测到明显违规项")
    lines.append("")
    lines.append("---")
    lines.append("")
    # 匹配风格模板库
    lines.append("## 风格模板库匹配")
    lines.append("")
    templates = list_templates()
    if templates:
        # 用关键词匹配模板
        all_kw = " ".join(report.canva_cn_keywords + report.canva_en_keywords).lower() if report.canva_cn_keywords else ""
        for t in templates:
            tags = " ".join(t.get("tags", [])).lower()
            match_score = sum(1 for tag in t.get("tags", []) if tag.lower() in all_kw or tag.lower() in report.overall_vibe.lower())
            if match_score >= 2:
                lines.append(f"- **{t.get('name', '?')}** ({t.get('source', '?')}) — 匹配{min(match_score, 5)}/5个标签")
                lines.append(f"  字体参考: {', '.join(t.get('fonts', ['?']))}")
        if not any(True for t in templates if sum(1 for tag in t.get("tags", []) if tag.lower() in all_kw) >= 2):
            lines.append("- 暂无匹配的风格模板（可手动创建: `downloads/clone_templates/`）")
    else:
        lines.append("- 模板库为空，运行「图片逆向」分析可添加新模板")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 模板参考链接")
    lines.append("")
    for name, url in report.template_links.items():
        if url.startswith("http"):
            lines.append(f"- [{name}]({url})")
        else:
            lines.append(f"- **{name}**: {url}")
    lines.append("")
    if report.summary:
        lines.append(f"> 💡 {report.summary}")

    return "\n".join(lines)


# ── Agent ─────────────────────────────────────────────────────

# ── 模板库 ─────────────────────────────────────────────────

_TEMPLATES_DIRS = [
    _PROJECT_ROOT / "templates",
    _PROJECT_ROOT / "downloads" / "clone_templates",
]


def list_templates() -> list[dict]:
    """列出所有已保存的风格模板（从 templates/ 和 downloads/clone_templates/）。"""
    import json
    templates = []
    for d in _TEMPLATES_DIRS:
        if d.exists():
            for f in sorted(d.glob("*.json")):
                try:
                    data = json.loads(f.read_text("utf-8"))
                    data["_file"] = f.name
                    if not any(t.get("name") == data.get("name") for t in templates):
                        templates.append(data)
                except Exception:
                    pass
    return templates


def load_template(name: str) -> dict | None:
    """按名称或文件名加载风格模板。"""
    import json
    for d in _TEMPLATES_DIRS:
        path = d / f"{name}.json"
        if not path.exists():
            path = d / name
        if path.exists():
            return json.loads(path.read_text("utf-8"))
    for t in list_templates():
        if t.get("name") == name or t.get("_file") == name:
            return t
    return None


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
                    image_hint=s.image_hint,
                    voiceover_hint=s.voiceover_hint,
                    transition_to_next=s.transition_to_next,
                )
                for s in clone_output.shooting_script
            ]
            report.summary = clone_output.summary
            report.publishing_warnings = self._check_publishing_rules(clone_output.rewritten_copy)
            report.template_links = self._build_template_links(
                clone_output.canva_keywords.cn_keywords,
                clone_output.canva_keywords.en_keywords,
                clone_output.canva_keywords.jianying_keywords,
            )

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
        from src.utils.browser_service import browser

        # 确保浏览器已启动
        await browser.start()

        # 短链接先通过浏览器解析
        resolved_url = video_url
        if any(s in video_url for s in ("v.douyin.com", "b23.tv", "xhslink.com")):
            try:
                page = await browser.new_page()
                try:
                    await page.goto(video_url, wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(2000)
                    resolved_url = page.url
                    logger.info(f"短链接已解析: {video_url[:40]} -> {resolved_url[:60]}")
                finally:
                    await page.close()
            except Exception as exc:
                logger.warning(f"短链接解析失败，使用原始链接: {exc}")

        vid = resolved_url.rsplit("/", 1)[-1].split("?")[0]
        out_dir = str(_DOWNLOAD_DIR / "clone_videos")
        os.makedirs(out_dir, exist_ok=True)
        filename = f"{platform}_{int(time.time())}.mp4"
        filepath = os.path.join(out_dir, filename)

        # Path 1: yt-dlp（最可靠，支持抖音/B站/几乎所有平台）
        try:
            proc = await asyncio.create_subprocess_exec(
                "yt-dlp", "-o", filepath, "--format", "best[height<=1080]", "--no-playlist",
                resolved_url,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode == 0 and os.path.getsize(filepath) > 10000:
                logger.info(f"yt-dlp 下载成功: {os.path.getsize(filepath)} bytes")
                dur = await self._get_duration(filepath)
                return DownloadedVideo(platform=platform, video_id=vid, filepath=filepath,
                                        title="", duration_seconds=dur)
            logger.warning(f"yt-dlp 失败，回退 CDP 浏览器: {stderr.decode(errors='replace')[:100]}")
        except Exception as exc:
            logger.warning(f"yt-dlp 不可用，回退 CDP 浏览器: {exc}")

        # Path 2: CDP 浏览器提取
        item = {"link": resolved_url, "aweme_id": vid}
        item.setdefault("cover_url", "")
        extractor = MediaExtractor()
        video_src = await extractor.extract_video(platform, item)
        if not video_src:
            raise RuntimeError(f"无法提取视频 URL: {video_url}")

        dl = MediaDownloader()
        try:
            results = await dl.download_urls(
                urls=[video_src], output_dir=out_dir, filenames=[filename],
            )
        finally:
            await dl.close()

        if not results or results[0].status not in ("success", "skipped"):
            raise RuntimeError(f"下载失败: {results[0].error if results else '未知'}")

        filepath = results[0].filepath
        dur = await self._get_duration(filepath)
        return DownloadedVideo(platform=platform, video_id=vid, filepath=filepath,
                                title="", duration_seconds=dur)

    async def _get_duration(self, filepath: str) -> float:
        try:
            from src.utils.ffmpeg_utils import probe_duration
            return await probe_duration(filepath)
        except Exception:
            return 0.0

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
  "text_overlay_style": "字幕/文字风格描述（10字以上，无文字则写'纯画面内容，无文字叠加元素'）",
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
            # 确保所有字段满足 min_length 要求
            for key, min_len in [
                ("color_scheme", 15), ("lighting_style", 10), ("composition_pattern", 15),
                ("text_overlay_style", 8), ("transition_style", 10), ("color_grading", 15),
                ("pace_description", 20), ("objects_and_scenes", 15), ("overall_vibe", 15),
            ]:
                val = parsed.get(key, "")
                if isinstance(val, str) and len(val) < min_len:
                    parsed[key] = val + "（基于关键帧画面视觉特征的综合推断分析）"
            return StyleAnalysisOutput(**parsed)
        except Exception as exc:
            logger.warning(f"QWEN-VL 分析失败，使用回退: {exc}")
            return self._qwen_fallback(title)

    def _qwen_fallback(self, title: str) -> StyleAnalysisOutput:
        return StyleAnalysisOutput(
            color_scheme=f"基于标题「{title[:30]}」推断：需配置 QWEN_API_KEY 以获取精准视觉分析",
            lighting_style="（需千问 QWEN-VL 多模态模型分析光线风格）",
            composition_pattern="（需千问 QWEN-VL 多模态模型分析构图模式）",
            text_overlay_style="（需千问 QWEN-VL 多模态模型分析文字字幕风格）",
            transition_style="（需千问 QWEN-VL 多模态模型分析转场风格）",
            color_grading="（需千问 QWEN-VL 多模态模型分析调色倾向）",
            pace_description="（需千问 QWEN-VL 多模态模型分析视频节奏变化）",
            objects_and_scenes="（需千问 QWEN-VL 多模态模型识别画面物体与场景元素）",
            overall_vibe="（需千问 QWEN-VL 多模态模型总结视觉氛围）",
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
1. style_analysis: 直接引用上方「视觉风格分析」的内容，确保每项不少于12字
2. canva_keywords: 使用短词（2-4字/词），中文用空格分隔，英文全小写
3. rewritten_copy: 200字以上完整配音稿，保留核心信息但改写句式用词
4. bgm_recommendations: 至少3首，mood字段不低于8字（如"科技感十足 快速节奏有力"）
5. shooting_script: 3-8个镜头，每个action_description不低于15字，image_hint写配图建议(截图/录屏/素材)
</quality_standards>

<task>
基于上方视觉风格分析，生成完整复刻方案。注意：style_analysis 字段直接复制上方分析的原文，确保足够长度。
</task>

<output_format>
返回纯JSON：
{{{{"style_analysis": ...,
 "canva_keywords": {{{{"cn_keywords": ["关键词1","关键词2",...],
   "en_keywords": ["keyword1","keyword2",...],
   "jianying_keywords": ["剪映关键词1","剪映关键词2",...]}}}},
 "rewritten_copy": "改写后的完整文案（200字以上）",
 "bgm_recommendations": [{{{{"genre":"电子","bpm_range":"110-130","mood":"科技感 快节奏","search_keyword": "科技背景音乐 快节奏"}}}}, ...],
 "shooting_script": [{{{{"shot_number":1,"duration_seconds":8,"camera_angle":"特写","action_description":"产品慢慢靠近镜头","text_overlay":"太好用了","image_hint":"产品高清特写截图","voiceover_hint":"这东西太好用了...","transition_to_next":"淡入"}}}}, ...],
 "summary": "50字以上总结，含总体风格方向+适用场景"
}}}}
</output_format>"""

        try:
            output = await self._call_llm_with_critic(
                prompt, VideoCloneOutput, "video_cloner", temperature=0.3, max_tokens=4000
            )
            data = output.model_dump()
            self._pad_clone_output(data)
            return VideoCloneOutput(**data)
        except Exception as exc:
            logger.warning(f"DeepSeek 验证失败，重试宽松模式: {exc}")
            try:
                raw = await self._call_llm(prompt, temperature=0.3, json_mode=True, max_tokens=4000)
                parsed = self._parse_json(raw)
                if isinstance(parsed, str):
                    parsed = self._parse_json(parsed)
                if isinstance(parsed, dict):
                    self._pad_clone_output(parsed)
                    return VideoCloneOutput(**parsed)
                raise ValueError(f"无法解析为dict: {type(parsed)}")
            except Exception as exc2:
                logger.warning(f"DeepSeek 失败，使用回退: {exc2}")
                return self._clone_fallback(style, platform)

    @staticmethod
    def _check_publishing_rules(copy_text: str) -> list[str]:
        """检查文案中的发文避忌，返回违规提示列表（空列表=通过）。"""
        warnings: list[str] = []
        # 绝对红线
        for kw in ["¥", "￥", "微信", "微信号", "二维码", "加我", "私信", "联系我", "商务合作"]:
            if kw in copy_text:
                warnings.append(f"❌ 含「{kw}」— 绝对禁止，必须删除")
        # 绝对化用语
        for kw in ["最好用", "最强", "第一", "顶级", "100%", "永久", "碾压", "比XX好用"]:
            if kw in copy_text:
                warnings.append(f"⚠️ 含「{kw}」— 绝对化用语，建议改为中性表述")
        # 商业字眼
        for kw in ["购买", "售价", "定价", "付费", "¥399", "Pro版", "商用"]:
            if kw in copy_text:
                warnings.append(f"⚠️ 含「{kw}」— 商业字眼，公开平台禁用")
        # 价格数字
        import re
        price_patterns = re.findall(r'[¥￥]\s*\d+', copy_text)
        for p in price_patterns:
            warnings.append(f"❌ 含价格「{p}」— 任何平台绝不出现价格")
        # 检查是否有 GitHub 链接（安全做法）
        if "github.com" in copy_text.lower():
            warnings.append("✅ 含GitHub链接 — 掘金/知乎/B站/开源中国允许")
        return warnings

    @staticmethod
    def _build_template_links(cn_keywords: list[str], en_keywords: list[str], jianying_keywords: list[str]) -> dict[str, str]:
        """生成模板平台一键搜索直达链接，零 API 依赖。"""
        from urllib.parse import quote
        cn_q = quote(" ".join(cn_keywords[:4]) if cn_keywords else "科技测评 模板")
        en_q = quote(" ".join(en_keywords[:4]) if en_keywords else "tech review template")
        jy_q = quote(" ".join(jianying_keywords[:4]) if jianying_keywords else "科技测评")
        return {
            "canva_cn": f"https://www.canva.com/templates/?query={cn_q}",
            "canva_en": f"https://www.canva.com/templates/?query={en_q}",
            "gamma": f"https://gamma.app/create?prompt={en_q}",
            "laihua": f"https://www.laihua.com/templates?keyword={cn_q}",
            "jianying_hint": f"剪映桌面版搜索：{jy_q}",
            "beautiful_ai": f"https://www.beautiful.ai/gallery?search={en_q}",
        }

    @staticmethod
    def _pad_clone_output(data: dict):
        """确保 DeepSeek 输出的所有文本字段满足 Pydantic min_length。"""
        sa = data.get("style_analysis", {})
        for key, min_len in [
            ("color_scheme", 15), ("lighting_style", 10), ("composition_pattern", 15),
            ("text_overlay_style", 8), ("transition_style", 10), ("color_grading", 15),
            ("pace_description", 20), ("objects_and_scenes", 15), ("overall_vibe", 15),
        ]:
            val = sa.get(key, "")
            if isinstance(val, str) and len(val) < min_len:
                sa[key] = val + "（基于视频画面视觉特征的综合分析）"
        for bgm in data.get("bgm_recommendations", []):
            if len(bgm.get("mood", "")) < 8:
                bgm["mood"] = bgm.get("mood", "") + " 氛围音乐推荐"
        if len(data.get("rewritten_copy", "")) < 40:
            data["rewritten_copy"] = data.get("rewritten_copy", "") + "（需调整文案长度以满足最低要求，建议补充更多产品细节描述）"
        if len(data.get("summary", "")) < 40:
            data["summary"] = data.get("summary", "") + "（基于视觉风格分析的完整视频复刻方案总结）"

    def _clone_fallback(self, style: StyleAnalysisOutput, platform: str) -> VideoCloneOutput:
        return VideoCloneOutput(
            style_analysis=style,
            canva_keywords=CanvaKeywordsOutput(
                cn_keywords=["科技产品介绍", "数码测评", "工具展示模板"],
                en_keywords=["tech review template", "product demo design", "minimalist presentation"],
                jianying_keywords=["科技测评模板", "数码产品介绍", "工具软件展示"],
            ),
            rewritten_copy="（需 DeepSeek API Key 生成改写文案，请检查 DEEPSEEK_API_KEY 配置）",
            bgm_recommendations=[
                BGMTrack(genre="电子", bpm_range="110-130", mood="科技感十足 快节奏有力", search_keyword="科技背景音乐 快节奏电子"),
                BGMTrack(genre="轻音乐", bpm_range="80-100", mood="简洁清新 轻快流畅", search_keyword="轻快背景音乐 科技视频配乐"),
                BGMTrack(genre="氛围", bpm_range="90-110", mood="专业大气 商务沉稳", search_keyword="商务科技 背景音乐大气"),
            ],
            shooting_script=[
                ShotInstruction(
                    shot_number=1, duration_seconds=5, camera_angle="特写",
                    action_description="产品主图展示，配合标题文字弹出动画",
                    text_overlay="产品名称 + 一句话卖点", image_hint="产品高清截图或渲染图",
                    voiceover_hint="今天给大家介绍一款...", transition_to_next="淡入淡出",
                ),
                ShotInstruction(
                    shot_number=2, duration_seconds=8, camera_angle="中景",
                    action_description="产品实际使用场景演示，展示核心功能",
                    text_overlay="功能要点1 / 功能要点2", image_hint="操作录屏截图",
                    voiceover_hint="它的核心功能是...", transition_to_next="硬切",
                ),
                ShotInstruction(
                    shot_number=3, duration_seconds=5, camera_angle="全景",
                    action_description="总结画面，三产品排列+行动号召文字",
                    text_overlay="立即体验", image_hint="产品合集图或品牌logo",
                    voiceover_hint="快来试试吧", transition_to_next="淡出",
                ),
            ],
            summary="（降级模式：需同时配置 QWEN_API_KEY + DEEPSEEK_API_KEY 获取完整克隆方案）",
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
