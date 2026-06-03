"""ffmpeg 智能抽帧 — 场景检测 + 均匀补充，适配 3-10 分钟视频。

用法:
    frames = await smart_extract_frames("video.mp4", "output_dir/")
"""

import asyncio
import json
import os
import shutil
from pathlib import Path

from src.utils.logger import logger

_FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
_FFPROBE = shutil.which("ffprobe") or "ffprobe"

MAX_WIDTH = 1280
JPEG_QUALITY = 3  # 2-31, 越低越好


# ── ffprobe 预扫描 ──────────────────────────────────────────

async def _run(*args, timeout: int = 120) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(stderr.decode(errors="replace")[:300])
    return stdout.decode(errors="replace") or stderr.decode(errors="replace")


async def probe_scenes(video_path: str) -> dict:
    """用 ffprobe 检测场景切换时间戳。"""
    try:
        out = await _run(
            _FFPROBE, "-v", "quiet",
            "-show_frames", "-of", "json",
            "-f", "lavfi", f"movie={video_path},select=gt(scene\\,0.4)",
        )
        frames = json.loads(out).get("frames", [])
        timestamps = [
            float(f.get("pkt_pts_time", 0))
            for f in frames
            if f.get("pkt_pts_time")
        ]
        return {
            "scene_timestamps": sorted(set(round(t, 1) for t in timestamps)),
            "scene_count": len(timestamps),
        }
    except Exception as exc:
        logger.warning(f"ffprobe 场景检测失败，使用均匀抽帧: {exc}")
        return {"scene_timestamps": [], "scene_count": 0}


async def probe_duration(video_path: str) -> float:
    """返回视频时长（秒）。"""
    try:
        out = await _run(
            _FFPROBE, "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            video_path,
        )
        return float(out.strip())
    except Exception:
        return 0.0


# ── 抽帧策略 ─────────────────────────────────────────────────

async def extract_keyframes_smart(
    video_path: str,
    output_dir: str,
    duration_seconds: float = 0.0,
    max_frames: int = 30,
    long_scene_interval: float = 10.0,
    scene_threshold: float = 0.4,
) -> list[str]:
    """根据视频时长智能抽帧。

    Args:
        video_path: 视频文件路径
        output_dir: 输出目录
        duration_seconds: 视频时长（0 则自动检测）
        max_frames: 总帧数上限
        long_scene_interval: 长场景补充间隔（秒）
        scene_threshold: 场景切换检测阈值 (0.1-1.0)

    Returns:
        输出帧文件路径列表
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"视频不存在: {video_path}")

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # 时长未知则自动检测
    if duration_seconds <= 0:
        duration_seconds = await probe_duration(video_path)

    # 根据时长调整参数
    if duration_seconds < 30:
        max_frames = 8
    elif duration_seconds < 180:
        max_frames = 20
        long_scene_interval = 5.0
    else:
        max_frames = max_frames
        long_scene_interval = long_scene_interval

    logger.info(
        f"智能抽帧: 时长={duration_seconds:.0f}s, 上限={max_frames}帧, "
        f"补充间隔={long_scene_interval}s"
    )

    # Round 1: 场景切换帧
    scene_timestamps = []
    try:
        scene_info = await probe_scenes(video_path)
        scene_timestamps = scene_info["scene_timestamps"]
        logger.info(f"检测到 {len(scene_timestamps)} 个场景切换")
    except Exception as exc:
        logger.warning(f"场景检测跳过: {exc}")

    max_scene = max_frames // 2
    scene_timestamps = scene_timestamps[:max_scene]

    # Round 2: 均匀补充帧（避免场景内漏掉关键画面）
    uniform_ts_list: list[float] = []
    if len(scene_timestamps) < max_frames:
        remaining = max_frames - len(scene_timestamps)
        step = max(long_scene_interval, duration_seconds / max(remaining, 1))
        uniform_ts_list = [
            round(t, 1)
            for t in [step * i for i in range(1, int(duration_seconds / step))]
            if t < duration_seconds - 1
        ][:remaining]

    # 合并去重、排序
    all_ts = sorted(set(scene_timestamps + uniform_ts_list))
    all_ts = all_ts[:max_frames]

    # 确保首帧
    if not any(t < 1.0 for t in all_ts):
        all_ts.insert(0, 0.5)

    all_ts = all_ts[:max_frames]

    # 逐时间戳抽帧
    paths = []
    for i, ts in enumerate(all_ts):
        out_path = os.path.join(output_dir, f"frame_{i:03d}_t{ts:.1f}s.jpg")
        try:
            await _run(
                _FFMPEG, "-y", "-ss", str(ts),
                "-i", video_path,
                "-vframes", "1",
                "-q:v", str(JPEG_QUALITY),
                "-vf", f"scale={MAX_WIDTH}:-2",
                out_path,
            )
            if os.path.getsize(out_path) > 500:
                paths.append(out_path)
            else:
                Path(out_path).unlink(missing_ok=True)
        except Exception as exc:
            logger.debug(f"抽帧失败 t={ts}s: {exc}")

    logger.info(f"抽帧完成: {len(paths)}/{len(all_ts)} 帧 ({duration_seconds:.0f}s 视频)")
    return paths


async def extract_keyframes_uniform(
    video_path: str,
    output_dir: str,
    duration_seconds: float = 0.0,
    interval: float = 3.0,
    max_frames: int = 20,
) -> list[str]:
    """均匀抽帧（备用方案，无 ffprobe 时使用）。"""
    if duration_seconds <= 0:
        duration_seconds = await probe_duration(video_path)
    if duration_seconds <= 0:
        duration_seconds = 60

    count = min(int(duration_seconds / interval), max_frames)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    paths = []
    for i in range(count):
        ts = interval * (i + 1)
        if ts >= duration_seconds - 1:
            break
        out_path = os.path.join(output_dir, f"frame_{i:03d}.jpg")
        try:
            await _run(
                _FFMPEG, "-y", "-ss", str(ts),
                "-i", video_path,
                "-vframes", "1",
                "-q:v", str(JPEG_QUALITY),
                "-vf", f"scale={MAX_WIDTH}:-2",
                out_path,
            )
            if os.path.getsize(out_path) > 500:
                paths.append(out_path)
        except Exception as exc:
            logger.debug(f"均匀抽帧失败 t={ts}s: {exc}")

    return paths
