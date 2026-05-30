"""Agent Trace Collector — 记录每次输出，Dynamic Few-Shot 自动注入。

核心机制：
1. 每次 Agent 成功输出 → 自动记录 trace
2. 下次同一 Agent 调用 → 自动注入历史高分输出作为 Dynamic Few-Shot
3. 实现业界验证的 +20-30% 提升

用法:
  from src.orchestrator.agents.trace_collector import record_trace, build_dynamic_fewshot
  record_trace("trend_scout", input_summary, output_dict, score=85)
  dyn_fs = build_dynamic_fewshot("trend_scout", min_score=75)
"""

import json
from datetime import datetime
from pathlib import Path

TRACE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "eval" / "traces"


def record_trace(agent_type: str, input_summary: dict, output_data: dict, score: float = 0.0):
    """记录一次 Agent 输出的完整 trace。"""
    TRACE_DIR.mkdir(parents=True, exist_ok=True)

    trace = {
        "timestamp": datetime.now().isoformat(),
        "agent_type": agent_type,
        "score": score,
        "input_summary": input_summary,
        "output_summary": str(output_data.get("summary", ""))[:300],
        "output": output_data,
    }

    filename = f"{agent_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{score:.0f}.json"
    filepath = TRACE_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(trace, f, ensure_ascii=False, indent=2)

    return str(filepath)


def get_top_traces(agent_type: str, min_score: float = 70.0, limit: int = 3) -> list:
    """获取某个 Agent 的高分 trace，按分数降序。"""
    if not TRACE_DIR.exists():
        return []

    traces = []
    for fname in sorted(TRACE_DIR.iterdir(), reverse=True):
        if not fname.name.startswith(agent_type) or not fname.suffix == ".json":
            continue
        try:
            trace = json.loads(fname.read_text("utf-8"))
            if trace.get("score", 0) >= min_score:
                traces.append(trace)
        except (json.JSONDecodeError, KeyError):
            continue

    traces.sort(key=lambda t: t.get("score", 0), reverse=True)
    return traces[:limit]


def build_dynamic_fewshot(agent_type: str, min_score: float = 70.0) -> str:
    """从高分 trace 构建 Dynamic Few-Shot 文本，注入 prompt。"""
    traces = get_top_traces(agent_type, min_score)
    if not traces:
        return ""

    lines = ["## 动态示例（本会话高分输出）"]
    for i, t in enumerate(traces):
        s = t.get("score", 0)
        output = t.get("output", {})
        summary = str(output.get("summary", ""))[:120]
        # 尝试提取 items 的第一个元素
        items = output.get("items") or output.get("breakdowns") or output.get("products") or output.get("variants") or output.get("tactics") or []
        if isinstance(items, list) and len(items) > 0:
            first = items[0]
            if isinstance(first, dict):
                first_str = json.dumps(first, ensure_ascii=False)[:150]
                summary += "\n  示例输出: " + first_str
        lines.append(f"\n### 示例{i+1}（评分{s:.0f}）\n{summary}")

    return "\n".join(lines)


if __name__ == "__main__":
    for agent in ["trend_scout", "copy_writer", "sentiment_reader"]:
        traces = get_top_traces(agent, min_score=70)
        print(f"{agent}: {len(traces)} high-score traces")
        fs = build_dynamic_fewshot(agent, min_score=70)
        if fs:
            print(f"  Dynamic Few-Shot: {len(fs)} chars")
