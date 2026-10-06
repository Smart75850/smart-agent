"""Test OUTPUT IN CHINESE invariant（章 4 Camel/BabyAGI 启发）。

按 invariant #14：所有 prompt 自动 inject "OUTPUT IN CHINESE"。

⚠️ 2026-10-06 重写原因：
原测试用 `inspect.getsource(agent._call_llm)` 断言源码文本里含某几个字符串。
这把「代码长什么样」当成了被测对象 —— 当日把注入逻辑抽成 `_inject_chinese_invariant`
（为了同时覆盖 `_call_qwen_vl` 多模态路径）之后，逻辑一字未改，3 个测试却全挂。
现全部改为**测真实行为**：打桩到 HTTP 层，直接检查真正发出去的 request body。
既不受重构影响，还顺带覆盖了此前完全没测的多模态路径。

⚠️ 2026-10-06 第二个坑：patch 的必须是 `base` 模块持有的那个 settings 实例。
项目里有 5 个测试文件（test_awel_operators / test_e2e_real_pipeline /
test_cross_verifier / test_meta_reviewer / test_video_cloner_memory）会
`importlib.reload(config.settings)` —— reload 造出一个**新的** settings 实例，
而 `base.py` 模块级 `from config.settings import settings` 仍绑在旧实例上。
若 patch `config.settings.settings`（新实例），被测代码读的还是旧实例：
本文件在全量测试里因此挂过（单独跑却过），且另外两条是「假过」
（断言恰好不受影响，patch 其实根本没生效）。故统一切到 `_base_mod.settings`
—— 也就是被测代码真正读取的那个对象。
"""

import base64
import types

import httpx as _real_httpx
import pytest

from src.orchestrator.agents import base as _base_mod
from src.orchestrator.agents.base import BaseAgent

# 1x1 透明 PNG —— 让 _call_qwen_vl 走真实读图分支（而非被 os.path.exists 跳过）
_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


class _FakeResponse:
    def __init__(self, status_code: int = 200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            req = _real_httpx.Request("POST", "http://fake/chat/completions")
            raise _real_httpx.HTTPStatusError(
                f"{self.status_code} error",
                request=req,
                response=_real_httpx.Response(self.status_code, request=req),
            )

    def json(self):
        return {"choices": [{"message": {"content": "ok"}}]}


def _install_fake_httpx(monkeypatch, captured: list, status_code: int = 200):
    """把 base 模块里的 httpx 换成本地替身；captured 收集每次发出的 body。

    只 patch `src.orchestrator.agents.base` 里的名字，不动全局 httpx。
    """

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None):
            captured.append({"url": url, "body": json})
            return _FakeResponse(status_code)

    from src.orchestrator.agents import base as base_mod
    monkeypatch.setattr(
        base_mod, "httpx", types.SimpleNamespace(AsyncClient=_FakeAsyncClient)
    )


# ── 注入逻辑本身 ────────────────────────────────────────────

def test_settings_default_chinese_invariant_true():
    """Test 1: settings 默认 CHINESE_OUTPUT_INVARIANT=True。"""
    assert _base_mod.settings.CHINESE_OUTPUT_INVARIANT is True, \
        "默认应该开 OUTPUT IN CHINESE"


def test_chinese_invariant_injects_when_missing(monkeypatch):
    """Test 2: 没 OUTPUT IN CHINESE 时自动 inject。"""
    monkeypatch.setattr(_base_mod.settings, "CHINESE_OUTPUT_INVARIANT", True)

    agent = BaseAgent()
    out = agent._inject_chinese_invariant("写一段文案")

    assert out.startswith("OUTPUT IN CHINESE"), "语言要求应注入到 prompt 头部"
    assert out.endswith("写一段文案"), "原始 prompt 必须完整保留"


def test_chinese_invariant_skipped_when_disabled(monkeypatch):
    """Test 3（failure path · 环境变化）: settings 关掉 invariant 后不 inject。"""
    monkeypatch.setattr(_base_mod.settings, "CHINESE_OUTPUT_INVARIANT", False)

    agent = BaseAgent()
    assert agent._inject_chinese_invariant("写一段文案") == "写一段文案"


def test_chinese_invariant_skipped_when_already_present(monkeypatch):
    """Test 4（failure path · 入口差异）: prompt 已带语言声明时不重复注入。"""
    monkeypatch.setattr(_base_mod.settings, "CHINESE_OUTPUT_INVARIANT", True)

    agent = BaseAgent()
    for already in ("OUTPUT IN CHINESE\n你好", "OUTPUT IN ENGLISH\nhello"):
        assert agent._inject_chinese_invariant(already) == already, \
            "已显式声明语言时，不得覆盖调用方的选择"


# ── 两条 LLM 路径真正发出去的东西 ───────────────────────────

@pytest.mark.asyncio
async def test_call_llm_sends_injected_prompt(monkeypatch):
    """Test 5: _call_llm 发到 HTTP 层的 body 里确实带着注入。"""
    captured: list = []
    _install_fake_httpx(monkeypatch, captured)

    agent = BaseAgent()
    await agent._call_llm("写一段文案")

    content = captured[0]["body"]["messages"][0]["content"]
    assert content.startswith("OUTPUT IN CHINESE")
    assert "写一段文案" in content


@pytest.mark.asyncio
async def test_call_qwen_vl_sends_injected_prompt(monkeypatch, tmp_path):
    """Test 6: 多模态路径 _call_qwen_vl 同样注入。

    这正是 2026-10-06 补漏的那条 —— 此前注入只写在 _call_llm 里，
    video_cloner.py:600 走的多模态路径输出语言完全不受控。
    """
    captured: list = []
    _install_fake_httpx(monkeypatch, captured)

    img = tmp_path / "1px.png"
    img.write_bytes(_PNG_1PX)

    agent = BaseAgent()
    await agent._call_qwen_vl("描述这张图", [str(img)])

    content = captured[0]["body"]["messages"][0]["content"]
    assert isinstance(content, list), "多模态走 content 数组"
    assert content[0]["type"] == "text"
    assert content[0]["text"].startswith("OUTPUT IN CHINESE"), \
        "多模态路径同样必须注入简体中文要求"
    assert len(content) == 2, "图片应作为第二个 content 元素随行"


@pytest.mark.asyncio
async def test_call_qwen_vl_injects_even_when_image_missing(monkeypatch, tmp_path):
    """Test 7（failure path · 数据完整性）: 图片路径不存在时跳过图片，文本仍注入。"""
    captured: list = []
    _install_fake_httpx(monkeypatch, captured)

    agent = BaseAgent()
    await agent._call_qwen_vl("描述这张图", [str(tmp_path / "不存在.png")])

    content = captured[0]["body"]["messages"][0]["content"]
    assert len(content) == 1, "不存在的图片应被跳过，不产生空图片块"
    assert content[0]["text"].startswith("OUTPUT IN CHINESE")


@pytest.mark.asyncio
async def test_call_qwen_vl_raises_on_http_error(monkeypatch, tmp_path):
    """Test 8（failure path · 兜底路径）: 后端 4xx/5xx 抛 HTTPStatusError。

    不加 raise_for_status 的话，错误会被后一行伪装成「QWEN-VL API 错误」，
    和 _call_llm 当年那个 KeyError: 'choices' 是同一种坑。
    """
    captured: list = []
    _install_fake_httpx(monkeypatch, captured, status_code=404)

    img = tmp_path / "1px.png"
    img.write_bytes(_PNG_1PX)

    agent = BaseAgent()
    with pytest.raises(_real_httpx.HTTPStatusError):
        await agent._call_qwen_vl("描述这张图", [str(img)])
