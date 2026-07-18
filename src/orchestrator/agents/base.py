"""Agent 基类 — 共享 LLM 配置和 HTTP 调用。"""

import base64
import json
import os
import re
from typing import TypeVar

import httpx
from pydantic import BaseModel

from config.settings import settings

T = TypeVar("T", bound=BaseModel)


class BaseAgent:
    def __init__(self):
        self._api_key = settings.DEEPSEEK_API_KEY or settings.LLM_API_KEY
        # Ollama 等本地模型唔需要 API key，塞 dummy 值绕过各 agent 的 key 检查
        if not self._api_key and settings.LLM_API_URL:
            self._api_key = "ollama"
        self._api_url = settings.DEEPSEEK_API_URL or settings.LLM_API_URL or "https://api.deepseek.com/v1"
        self._model = settings.DEEPSEEK_MODEL or settings.LLM_MODEL or "deepseek-chat"
        # QWEN-VL 多模态配置
        self._qwen_api_key = settings.QWEN_API_KEY or settings.LLM_API_KEY or self._api_key
        self._qwen_api_url = settings.QWEN_API_URL or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self._qwen_model = settings.QWEN_MODEL or "qwen-vl-max"

    async def _call_llm(self, prompt: str, temperature: float = 0.7, json_mode: bool = False, max_tokens: int = 4096) -> str:
        """调用 DeepSeek LLM，返回原始响应文本。

        max_tokens 默认 4096 因为 Qwen3.6 thinking mode 较长（800-2000 tokens），
        低于 2048 会被 thinking 抢光 quota 导致 response 为空。
        """
        body = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._api_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def _call_qwen_vl(
        self,
        prompt: str,
        images: list[str],
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> str:
        """调用 QWEN-VL 多模态模型，发送图片+文本并返回响应。

        Args:
            prompt: 文本提示
            images: 图片文件路径列表
            temperature: 采样温度
            max_tokens: 最大输出 token 数
        """
        content: list[dict] = [{"type": "text", "text": prompt}]
        for img_path in images:
            if not os.path.exists(img_path):
                continue
            ext = os.path.splitext(img_path)[1].lower().lstrip(".")
            mime = "jpeg" if ext in ("jpg", "jpeg") else ext
            with open(img_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/{mime};base64,{b64}"},
            })

        body = {
            "model": self._qwen_model,
            "messages": [{"role": "user", "content": content}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self._qwen_api_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._qwen_api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            data = resp.json()
            if "choices" not in data:
                raise RuntimeError(f"QWEN-VL API 错误: {data}")
            return data["choices"][0]["message"]["content"]

    async def _call_llm_structured(self, prompt, output_model, temperature=0.3, max_tokens=4000):
        schema = output_model.model_json_schema()
        schema_str = json.dumps(schema, ensure_ascii=False)
        full_prompt = f"{prompt}\n\n---\n输出必须严格符合以下 JSON Schema，只返回纯 JSON 对象：\n```json\n{schema_str}\n```"
        content = await self._call_llm(full_prompt, temperature=temperature, json_mode=True, max_tokens=max_tokens)
        parsed = self._parse_json(content)
        return output_model.model_validate(parsed)

    async def _call_llm_with_critic(self, prompt, output_model, agent_type, temperature=0.3, max_tokens=4000):
        from src.orchestrator.agents.critic import CriticAgent, CRITIC_CONFIG
        from src.orchestrator.agents.trace_collector import build_dynamic_fewshot, record_trace
        dyn_fs = build_dynamic_fewshot(agent_type, min_score=80)
        if dyn_fs: prompt = f"{prompt}\n\n{dyn_fs}"
        if not CRITIC_CONFIG.get("enabled", True): return await self._call_llm_structured(prompt, output_model, temperature, max_tokens)
        if agent_type not in CRITIC_CONFIG.get("agents", []): return await self._call_llm_structured(prompt, output_model, temperature, max_tokens)
        critic = CriticAgent(agent_type)
        feedback = ""
        for attempt in range(CRITIC_CONFIG.get("max_retry", 2) + 1):
            fb_prompt = f"## ⚠️ 上次输出质量问题（请务必修正）\n{feedback}\n\n---\n\n{prompt}" if feedback else prompt
            output = await self._call_llm_structured(fb_prompt, output_model, temperature, max_tokens)
            if attempt >= CRITIC_CONFIG.get("max_retry", 2): return output
            output_dict = output.model_dump()
            critic_result = await critic.review(output_dict, "", feedback)
            if critic_result.passed:
                try: record_trace(agent_type, {"score": critic_result.score}, output_dict, critic_result.score)
                except: pass
                return output
            from src.utils.logger import logger
            logger.info(f"Critic [{agent_type}] retry{attempt+1} score={critic_result.score}")
            feedback = critic_result.feedback
        return output

    @staticmethod
    def _parse_json(text: str) -> dict:
        """解析 LLM 返回的 JSON，处理常见格式问题。"""
        # 1. 去掉 markdown 代码块
        text = re.sub(r'```(?:json)?\s*\n?', '', text)
        text = re.sub(r'\n?```', '', text)
        text = text.strip()

        # 2. 找到最外层 JSON 对象或数组
        for open_c, close_c in [('{', '}'), ('[', ']')]:
            start = text.find(open_c)
            if start == -1:
                continue
            depth = 0
            end = -1
            for i in range(start, len(text)):
                if text[i] == open_c:
                    depth += 1
                elif text[i] == close_c:
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end > start:
                text = text[start:end]
                break

        # 3. 去掉尾部逗号 + 双逗号
        text = re.sub(r',\s*([}\]])', r'\1', text)
        text = re.sub(r',\s*,', ',', text)

        # 4. 尝试标准解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 5. 宽松模式：替换字符串值内未转义的控制字符
        # 在 JSON 字符串值内 (":"..." 或 ":"...",)，将裸换行/制表符转义
        def _escape_in_strings(m: re.Match) -> str:
            inner = m.group(1)
            inner = inner.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
            return m.group(0)[0] + inner + m.group(0)[-1]

        # 匹配 ": "..." 中的字符串内容
        text = re.sub(
            r'(?<=:\s")((?:[^"\\]|\\.)*?)(?="\s*[,}\]])',
            _escape_in_strings,
            text,
            flags=re.DOTALL,
        )
        # 匹配 "..." 在数组中的情况
        text = re.sub(
            r'(?<=\[\s")((?:[^"\\]|\\.)*?)(?="\s*[,}\]])',
            _escape_in_strings,
            text,
            flags=re.DOTALL,
        )

        return json.loads(text)

