#!/usr/bin/env python3
"""知识星图 MCP Server — 标准化接口，供Claude Code/Codex/Hermes等Agent调用"""
import json
import sys
import os
from pathlib import Path

# 添加脚本目录到路径
sys.path.insert(0, str(Path(__file__).parent))
from match_knowledge import (
    load_knowledge, save_knowledge, validate_knowledge,
    extract_keywords, match_knowledge, get_recommendations,
    update_mastery, update_view_count, generate_report,
    check_prereqs, check_outdated, check_unmastered_prereqs,
)

# MCP 工具定义
TOOLS = [
    {
        "name": "knowledge_init",
        "description": "初始化知识星图，返回知识点总数和领域分布",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "knowledge_match",
        "description": "根据任务描述匹配相关知识点",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "任务描述或关键词"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "knowledge_recommend",
        "description": "获取学习路径推荐",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "knowledge_report",
        "description": "生成学习周报",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "knowledge_update_mastery",
        "description": "更新指定知识点的掌握度",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "知识点ID"},
                "delta": {"type": "integer", "description": "掌握度变化量(正数增加,负数减少)", "default": 1}
            },
            "required": ["id"]
        }
    },
    {
        "name": "knowledge_check_prereqs",
        "description": "检查知识点前置依赖是否完成",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "知识点ID"}
            },
            "required": ["id"]
        }
    },
    {
        "name": "knowledge_outdated",
        "description": "检查超过N天未复习的知识点",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "天数阈值，默认30", "default": 30}
            },
            "required": []
        }
    },
    {
        "name": "knowledge_status",
        "description": "综合学习状态报告",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
]


def handle_request(request: dict) -> dict:
    """处理MCP请求"""
    method = request.get("method", "")
    req_id = request.get("id", 0)

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = request.get("params", {})
        tool_name = params.get("name", "")
        args = params.get("arguments", {})

        try:
            knowledge = load_knowledge()
            if not knowledge:
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": "[ERROR] 知识数据加载失败"}]}}

            result_text = ""

            if tool_name == "knowledge_init":
                cats = {}
                for k in knowledge:
                    cat = k.get("cat", "unknown")
                    cats[cat] = cats.get(cat, 0) + 1
                result_text = f"[OK] 知识星图已加载，共 {len(knowledge)} 个知识点\n\n领域分布：\n"
                for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
                    result_text += f"  - {cat}: {cnt}个\n"

            elif tool_name == "knowledge_match":
                query = args.get("query", "")
                keywords = extract_keywords(query)
                matches = match_knowledge(keywords, knowledge)
                if matches:
                    result_text = f"[FOUND] 找到 {len(matches)} 个相关知识点：\n\n"
                    for m in matches:
                        result_text += f"【{m['title']}】(掌握度:{m.get('mastery',0)}/5)\n"
                        result_text += f"  摘要: {m.get('summary','')}\n"
                        result_text += f"  匹配关键词: {', '.join(m.get('matched_keywords',[]))}\n\n"
                        update_view_count(m.get("id"))
                else:
                    result_text = "[SEARCH] 未找到相关知识点"

            elif tool_name == "knowledge_recommend":
                recs = get_recommendations(knowledge)
                result_text = "[PATH] 推荐学习路径：\n\n"
                for i, rec in enumerate(recs[:5], 1):
                    mastery = rec.get("mastery", 0)
                    pre_ok = "OK" if rec.get("pre_completed") else "前置未完成"
                    result_text += f"{i}. {rec.get('title','')} (掌握度:{mastery}/5 | {pre_ok})\n"

            elif tool_name == "knowledge_report":
                result_text = generate_report(knowledge)

            elif tool_name == "knowledge_update_mastery":
                kid = args.get("id", 0)
                delta = args.get("delta", 1)
                if update_mastery(kid, delta):
                    result_text = f"[OK] 知识点 {kid} 掌握度已更新(变化:{delta:+d})"
                else:
                    result_text = f"[ERROR] 更新知识点 {kid} 失败"

            elif tool_name == "knowledge_check_prereqs":
                kid = args.get("id", 0)
                result_text = check_prereqs(knowledge, kid)

            elif tool_name == "knowledge_outdated":
                days = args.get("days", 30)
                outdated = check_outdated(knowledge, days)
                if outdated:
                    result_text = f"[OUTDATED] {len(outdated)} 个知识点超过{days}天未复习：\n\n"
                    for k in outdated[:10]:
                        result_text += f"  {k['days_ago']}天前 — {k['title']} (掌握度:{k.get('mastery',0)}/5)\n"
                else:
                    result_text = f"[OK] 所有知识点都在{days}天内复习过"

            elif tool_name == "knowledge_status":
                total = len(knowledge)
                mastered = sum(1 for k in knowledge if k.get("mastery", 0) >= 4)
                learning = sum(1 for k in knowledge if 2 <= k.get("mastery", 0) < 4)
                outdated = check_outdated(knowledge, 30)
                result_text = f"[STATUS] 知识星图学习状态\n\n"
                result_text += f"总计: {total} | 已掌握: {mastered}({round(mastered/total*100)}%) | 学习中: {learning}\n"
                if outdated:
                    result_text += f"\n{len(outdated)}个知识点超过30天未复习\n"
                recs = get_recommendations(knowledge)
                if recs:
                    result_text += f"\n推荐下一步:\n"
                    for i, rec in enumerate(recs[:3], 1):
                        result_text += f"  {i}. {rec['title']} (掌握度:{rec.get('mastery',0)}/5)\n"

            else:
                return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}}

            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": result_text}]}}

        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": str(e)}}

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32600, "message": "Invalid request"}}


def main():
    """stdio MCP Server 主循环"""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        except json.JSONDecodeError:
            continue


if __name__ == "__main__":
    main()
