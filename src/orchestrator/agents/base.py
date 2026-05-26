"""Agent 基类 — 共享 LLM 配置和 HTTP 调用。"""

import json
import re

import httpx

from config.settings import settings


class BaseAgent:
    def __init__(self):
        self._api_key = settings.DEEPSEEK_API_KEY or settings.LLM_API_KEY
        self._api_url = settings.DEEPSEEK_API_URL or settings.LLM_API_URL or "https://api.deepseek.com/v1"
        self._model = settings.DEEPSEEK_MODEL or settings.LLM_MODEL or "deepseek-chat"

    async def _call_llm(self, prompt: str, temperature: float = 0.7) -> str:
        """调用 DeepSeek LLM，返回原始响应文本。"""
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._api_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": 2000,
                },
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    @staticmethod
    def _parse_json(text: str) -> dict:
        """解析 LLM 返回的 JSON，处理常见格式问题。

        处理：markdown 代码块、首尾非 JSON 文本、尾部逗号。
        """
        # 1. 去掉 markdown 代码块
        text = re.sub(r'```(?:json)?\s*\n?', '', text)
        text = re.sub(r'\n?```', '', text)
        text = text.strip()

        # 2. 找到最外层 JSON 对象或数组
        # 优先找 { }，其次 [ ]
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

        # 3. 去掉尾部逗号 (在 ] 或 } 之前)
        text = re.sub(r',\s*([}\]])', r'\1', text)

        return json.loads(text)

