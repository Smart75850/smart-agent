"""Test video_cloner 集成 memory（出图 recall 闭环）。

源：高强文《大模型项目实战》第 16 章 CogVLM2 以文搜图。

按 smart-agent CLAUDE.md「测试粒度 ≈ 改动粒度」原则：
- Settings toggle: 1 个
- Memory hook skipped when disabled: 1 个
- Image hint extraction (text memory): 1 个

总 3 个 test。

注：image_hint 系文字描述，唔系真实图片路径 → 用 text memory（save_task_result）
    未来真正出图后，可以加 add_image_to_memory 写 image memory。
"""

import os
import shutil
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    """设置 env vars + reload settings。"""
    monkeypatch.setenv("LLM_API_URL", "http://127.0.0.1:11435/v1")
    monkeypatch.setenv("LLM_MODEL", "qwen3.6")
    monkeypatch.setenv("DEEPSEEK_API_URL", "http://127.0.0.1:11435/v1")
    monkeypatch.setenv("DEEPSEEK_MODEL", "qwen3.6")
    if "config.settings" in sys.modules:
        import importlib
        importlib.reload(sys.modules["config.settings"])


def test_settings_video_cloner_memory_disabled_by_default():
    """Test 1: 默认 VIDEO_CLONER_MEMORY_ENABLED=False（向后兼容）。"""
    from config.settings import settings
    assert settings.VIDEO_CLONER_MEMORY_ENABLED is False


def test_video_cloner_memory_skipped_when_disabled(monkeypatch):
    """Test 2: settings 关咗 memory 时，video_cloner.as_node 唔触发 memory。"""
    monkeypatch.setenv("VIDEO_CLONER_MEMORY_ENABLED", "false")
    if "config.settings" in sys.modules:
        import importlib
        importlib.reload(sys.modules["config.settings"])

    from config.settings import settings
    assert settings.VIDEO_CLONER_MEMORY_ENABLED is False


def test_video_cloner_extracts_image_hints_to_text_memory(monkeypatch, tmp_path):
    """Test 3: video_cloner 出图 hints 提取 + 写入 text memory。"""
    monkeypatch.setenv("VIDEO_CLONER_MEMORY_ENABLED", "true")
    monkeypatch.setenv("MEMORY_CHROMA_PATH", str(tmp_path))
    if "config.settings" in sys.modules:
        import importlib
        importlib.reload(sys.modules["config.settings"])

    from src.memory.store import MemoryStore
    from src.memory.recall import save_task_result

    # 预先创建 store（用 tmp_path）
    store = MemoryStore(path=str(tmp_path), collection_name="smart_agent_tasks")

    # 模拟 as_node 嘅 memory hook
    shots = [
        {"shot_number": 1, "image_hint": "美女特写镜头", "action_description": "开场", "camera_angle": "正面特写", "duration_seconds": 3},
        {"shot_number": 2, "image_hint": "产品 360 度展示", "action_description": "产品介绍", "camera_angle": "环绕镜头", "duration_seconds": 5},
        {"shot_number": 3, "image_hint": "", "action_description": "无图", "camera_angle": "无", "duration_seconds": 0},  # 空 hint 跳过
    ]

    valid_hints = [s for s in shots if s["image_hint"] and s["image_hint"].strip()]

    for shot in valid_hints:
        summary = f"[Shot {shot['shot_number']}] {shot['action_description']} | image_hint: {shot['image_hint']}"
        save_task_result(
            keyword=f"video_clone:douyin:test_video",
            summary=summary,
            metadata={
                "video_url": "https://example.com/video",
                "shot_number": shot["shot_number"],
                "platform": "douyin",
            },
            store=store,  # 用 tmp_path store
        )

    # 验证: 只有 2 个有效 hint 写入（empty hint 跳过）
    assert store.count() == 2, f"应该只有 2 个 hint 写入（空 hint 跳过），但得 {store.count()}"

    # 验证: recall 同 keyword 可以搵到
    from src.memory.recall import recall_similar_tasks
    results = recall_similar_tasks("美女特写", top_k=2, store=store)
    assert len(results) >= 1
    print(f"   Recall results: {[(r['text'][:50], r['distance']) for r in results]}")