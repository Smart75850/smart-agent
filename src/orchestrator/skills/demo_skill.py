"""Demo Skill — 验证 Skill 抽象可以 work。

用途：
  - 喺 graph 之外独立测试 Skill 接口
  - 作为新 Skill 嘅模板
  - 验证 Registry 模式

唔同现有 7 agent 集成，纯 demo。
"""

from __future__ import annotations
from src.orchestrator.skills.base import Skill


class DemoSkill(Skill):
    """最简单嘅 Skill 实现，验证接口。"""

    name = "demo_skill"
    description = "Demo skill：echo 输入 state 嘅 keyword，返回 hello message。"

    async def execute(self, state: dict) -> dict:
        keyword = state.get("keyword", "")
        return {
            "demo_output": f"DemoSkill 收到 keyword='{keyword}'，skill 抽象 OK",
        }

    def to_tool_def(self) -> dict:
        """Override 提供更详细嘅 parameters schema。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "搜索关键词",
                        }
                    },
                    "required": ["keyword"],
                },
            },
        }