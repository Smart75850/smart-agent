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

    async def _call_llm(self, prompt: str, temperature: float = 0.7, json_mode: bool = False) -> str:
        """调用 DeepSeek LLM，返回原始响应文本。"""
        body = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": 2000,
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

