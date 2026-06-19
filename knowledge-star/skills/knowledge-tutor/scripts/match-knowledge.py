#!/usr/bin/env python3
"""
知识星图自动教学系统 - 匹配引擎 v2
数据源: knowledge-galaxy-data.json (独立JSON文件, 非HTML正则解析)
"""
import json
import re
import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any

# 跨平台路径检测：优先用 Git 仓库（多地同步），其次本地路径
def _find_galaxy_json() -> Path:
    """自动检测知识星图数据文件位置，兼容 Windows/Mac/Linux。"""
    candidates = [
        # Git 仓库优先（跨平台同步）
        Path(__file__).resolve().parent.parent.parent.parent.parent / "workspace" / "smart-agent" / "knowledge-star" / "knowledge-galaxy-data.json",
        # Windows 旧路径
        Path(os.environ.get("USERPROFILE", "")) / "Saved Games" / "knowledge-galaxy-data.json",
        # Mac/Linux
        Path.home() / "Saved Games" / "knowledge-galaxy-data.json",
        Path.home() / ".claude" / "knowledge-star" / "knowledge-galaxy-data.json",
        # 当前脚本目录下
        Path(__file__).resolve().parent / "knowledge-galaxy-data.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    # 默认返回第一个（让后续逻辑报错）
    return candidates[0]

def _find_report_path() -> Path:
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent.parent / "workspace" / "smart-agent" / "knowledge-star" / "knowledge-report.md",
        Path(os.environ.get("USERPROFILE", "")) / "Saved Games" / "knowledge-report.md",
        Path.home() / "Saved Games" / "knowledge-report.md",
        Path.home() / ".claude" / "knowledge-star" / "knowledge-report.md",
    ]
    for p in candidates:
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    return candidates[-1]

GALAXY_JSON = _find_galaxy_json()
REPORT_PATH = _find_report_path()

CAT_LABELS = {
    "python": "派森", "ai": "人工智能", "product": "产品",
    "reverse": "逆向", "frontend": "前端",
}

def load_knowledge():
    if not GALAXY_JSON.exists():
        print(f"[ERROR] 数据文件不存在: {GALAXY_JSON}", file=sys.stderr)
        return []
    try:
        return json.loads(GALAXY_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ERROR] JSON加载失败: {e}", file=sys.stderr)
        return []

def save_knowledge(data):
    tmp = GALAXY_JSON.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(GALAXY_JSON)
        return True
    except Exception as e:
        print(f"[ERROR] 保存失败: {e}", file=sys.stderr)
        return False

def validate_knowledge(data):
    result = {"valid": True, "errors": [], "warnings": [], "stats": {"total": len(data), "cats": {}}}
    ids = {d["id"] for d in data}
    for d in data:
        cat = d.get("cat", "unknown")
        result["stats"]["cats"][cat] = result["stats"]["cats"].get(cat, 0) + 1
        m = d.get("mastery", 0)
        if not (1 <= m <= 5):
            result["errors"].append(f"节点{d['id']}: mastery={m} 超出1-5范围")
            result["valid"] = False
        for r in d.get("rel", []):
            if r not in ids:
                result["errors"].append(f"节点{d['id']}: rel引用不存在的节点{r}")
                result["valid"] = False
        for p in d.get("pre", []):
            if p not in ids:
                result["errors"].append(f"节点{d['id']}: pre引用不存在的节点{p}")
                result["valid"] = False
    return result

def update_mastery(knowledge_id, mastery_delta=1):
    data = load_knowledge()
    if not data: return False
    for node in data:
        if node.get("id") == knowledge_id:
            node["mastery"] = max(1, min(5, node.get("mastery", 3) + mastery_delta))
            node["lv"] = datetime.now().strftime("%Y-%m-%d")
            return save_knowledge(data)
    print(f"[ERROR] 未找到知识点: {knowledge_id}", file=sys.stderr)
    return False

def update_view_count(knowledge_id):
    data = load_knowledge()
    if not data: return False
    for node in data:
        if node.get("id") == knowledge_id:
            node["vc"] = node.get("vc", 0) + 1
            node["lv"] = datetime.now().strftime("%Y-%m-%d")
            return save_knowledge(data)
    print(f"[ERROR] 未找到知识点: {knowledge_id}", file=sys.stderr)
    return False

def extract_keywords(text):
    stop_words = {"的","了","在","是","我","有","和","就","不","人","都","一","一个","上","也","很","到","说","要","去","你","会","着","没有","看","好","自己","这"}
    cn_words = re.findall(r"[一-龥]{2,4}", text)
    en_words = re.findall(r"[a-zA-Z]+", text)
    keywords = list(set(cn_words + en_words))
    return [kw for kw in keywords if kw not in stop_words]

def match_knowledge(keywords, knowledge, top_n=5):
    matches = []
    for item in knowledge:
        score = 0
        matched_keywords = []
        for kw in keywords:
            kwl = kw.lower()
            if kwl in item.get("title", "").lower():
                score += 3; matched_keywords.append(kw)
            if kwl in item.get("summary", "").lower():
                score += 2; matched_keywords.append(kw)
            if kwl in item.get("content", "").lower():
                score += 1; matched_keywords.append(kw)
            if kwl in item.get("cat", "").lower():
                score += 2; matched_keywords.append(kw)
        if score > 0:
            matches.append({**item, "match_score": score, "matched_keywords": list(set(matched_keywords))})
    matches.sort(key=lambda x: x["match_score"], reverse=True)
    return matches[:top_n]

def get_recommendations(knowledge):
    recommendations = []
    for item in knowledge:
        mastery = item.get("mastery", 0)
        vc = item.get("vc", 0)
        pre = item.get("pre", [])
        pre_completed = all(
            any(k.get("id") == pid and k.get("mastery", 0) >= 3 for k in knowledge)
            for pid in pre
        ) if pre else True
        score = 0
        if mastery < 3: score += 10
        if vc >= 8: score += 5
        if pre_completed: score += 6
        if score > 0:
            recommendations.append({**item, "recommend_score": score, "pre_completed": pre_completed})
    recommendations.sort(key=lambda x: x["recommend_score"], reverse=True)
    return recommendations[:10]

def generate_report(knowledge):
    now = datetime.now()
    total = len(knowledge)
    mastered = sum(1 for k in knowledge if k.get("mastery", 0) >= 4)
    learning = sum(1 for k in knowledge if 2 <= k.get("mastery", 0) < 4)
    new_items = sum(1 for k in knowledge if k.get("mastery", 0) <= 1)
    categories = {}
    for k in knowledge:
        cat = k.get("cat", "unknown")
        categories[cat] = categories.get(cat, 0) + 1
    cat_lines = []
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        label = CAT_LABELS.get(cat, cat)
        cat_lines.append(f"- {label}({cat}): {count}个知识点")
    report = f"""[REPORT] 知识星图学习周报
生成时间：{now.strftime("%Y-%m-%d %H:%M")}

[STATS] 掌握度统计：
- 总知识点：{total}
- 已掌握（4-5星）：{mastered}
- 学习中（2-3星）：{learning}
- 未接触（1星）：{new_items}

[FOLDER] 领域分布：
""" + "\n".join(cat_lines)
    recommendations = get_recommendations(knowledge)
    if recommendations:
        report += "\n[PATH] 推荐学习路径：\n"
        for i, rec in enumerate(recommendations[:5], 1):
            mastery = rec.get("mastery", 0)
            status = "[DONE]" if mastery >= 3 else "[LEARNING]" if mastery >= 2 else "[TODO]"
            pre_ok = "OK" if rec.get("pre_completed") else "前置未完成"
            report += f"{i}. {status} {rec.get('title', '')} (掌握度:{mastery}星 | {pre_ok})\n"
    return report

def format_match_result(match):
    mastery = match.get("mastery", 0)
    stars = mastery
    proj_str = ", ".join(match.get("proj", [])) or "无"
    kw_str = ", ".join(match.get("matched_keywords", []))
    return f"""[KNOWLEDGE] {match.get('title', '')}
- 摘要：{match.get('summary', '')}
- 掌握度：{stars}/5
- 相关项目：{proj_str}
- 匹配关键词：{kw_str}"""

def check_prereqs(knowledge, node_id):
    """检查知识点前置依赖是否满足"""
    node = next((k for k in knowledge if k["id"] == node_id), None)
    if not node:
        return f"[ERROR] 未找到知识点: {node_id}"
    pre_ids = node.get("pre", [])
    if not pre_ids:
        return f"[OK] 「{node['title']}」无前置依赖，可直接学习"
    lines = [f"前置依赖检查：「{node['title']}」(掌握度:{node.get('mastery',0)}/5)"]
    all_ok = True
    for pid in pre_ids:
        pn = next((k for k in knowledge if k["id"] == pid), None)
        if not pn:
            lines.append(f"  [X] 前置节点{pid}不存在")
            all_ok = False
        elif pn.get("mastery", 0) < 3:
            lines.append(f"  [!] {pn['title']} — 掌握度{pn.get('mastery',0)}/5（未达标, 需≥3）")
            all_ok = False
        else:
            lines.append(f"  [OK] {pn['title']} — 掌握度{pn.get('mastery',0)}/5（已达标）")
    if all_ok:
        lines.append("\n[OK] 所有前置依赖已完成，可以开始学习！")
    else:
        lines.append(f"\n[!] 有{sum(1 for pid in pre_ids if next((k for k in knowledge if k['id']==pid),{}).get('mastery',0)<3)}个前置依赖未完成，建议先补这些")
    return "\n".join(lines)

def check_outdated(knowledge, days=30):
    """检查超过N天未查看的知识点"""
    now = datetime.now()
    outdated = []
    for k in knowledge:
        lv = k.get("lv")
        if lv:
            try:
                last = datetime.strptime(lv, "%Y-%m-%d")
                if (now - last).days > days:
                    outdated.append({**k, "days_ago": (now - last).days})
            except ValueError:
                pass
    return sorted(outdated, key=lambda x: -x["days_ago"])

def check_unmastered_prereqs(knowledge, node_id):
    """检查并返回未完成的前置依赖列表（供match输出用）"""
    node = next((k for k in knowledge if k["id"] == node_id), None)
    if not node: return []
    pre_ids = node.get("pre", [])
    unmet = []
    for pid in pre_ids:
        pn = next((k for k in knowledge if k["id"] == pid), None)
        if pn and pn.get("mastery", 0) < 3:
            unmet.append(pn)
    return unmet

def main():
    parser = argparse.ArgumentParser(description="知识星图自动教学系统 v2")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--match", type=str)
    parser.add_argument("--update", type=int)
    parser.add_argument("--mastery", type=int, default=1)
    parser.add_argument("--view", type=int)
    parser.add_argument("--recommend", action="store_true")
    parser.add_argument("--recommend-path", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--check-prereqs", type=int, help="检查指定知识点的前置依赖")
    parser.add_argument("--outdated", nargs="?", type=int, const=30, default=None, help="检查N天未复习的知识点(默认30天)")
    parser.add_argument("--status", action="store_true", help="综合学习状态报告")
    args = parser.parse_args()

    knowledge = load_knowledge()
    if not knowledge:
        sys.exit(1)

    if args.validate:
        result = validate_knowledge(knowledge)
        print(f"知识点: {result['stats']['total']} 个")
        for cat, cnt in result["stats"]["cats"].items():
            print(f"  {cat}: {cnt}")
        if result["errors"]:
            print(f"\n  {len(result['errors'])}个错误:")
            for e in result["errors"]:
                print(f"  - {e}")
        else:
            print("\n  数据完整性检查通过")

    elif args.init:
        print(f"[OK] 知识星图已加载，共 {len(knowledge)} 个知识点\n")
        print("[FOLDER] 领域分布：")
        cats = {}
        for k in knowledge:
            cat = k.get("cat", "unknown")
            cats[cat] = cats.get(cat, 0) + 1
        for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
            label = CAT_LABELS.get(cat, cat)
            print(f"  - {label}: {cnt}个")

    elif args.match:
        keywords = extract_keywords(args.match)
        matches = match_knowledge(keywords, knowledge)
        if matches:
            print(f"[FOUND] 找到 {len(matches)} 个相关知识点：\n")
            for match in matches:
                print(format_match_result(match))
                # 前置依赖警告
                unmet = check_unmastered_prereqs(knowledge, match.get("id"))
                if unmet:
                    print(f"  [!] 前置依赖未完成: {', '.join(p['title']+'('+str(p.get('mastery',0))+'/5)' for p in unmet)}")
                update_view_count(match.get("id"))
        else:
            print("[SEARCH] 未找到相关知识点")

    elif args.update:
        if update_mastery(args.update, args.mastery):
            print(f"[OK] 知识点 {args.update} 掌握度已更新")

    elif args.view:
        if update_view_count(args.view):
            print(f"[OK] 知识点 {args.view} 查看次数已更新")

    elif args.check_prereqs:
        print(check_prereqs(knowledge, args.check_prereqs))

    elif args.outdated:
        outdated = check_outdated(knowledge, args.outdated)
        if outdated:
            print(f"[OUTDATED] {len(outdated)} 个知识点超过{args.outdated}天未复习：\n")
            for k in outdated[:10]:
                print(f"  {k['days_ago']}天前 — {k['title']} (掌握度:{k.get('mastery',0)}/5)")
        else:
            print(f"[OK] 所有知识点都在{args.outdated}天内复习过")

    elif args.status:
        total = len(knowledge)
        cats = {}
        for k in knowledge:
            cats[k.get("cat","unknown")] = cats.get(k.get("cat","unknown"), 0) + 1
        mastered = sum(1 for k in knowledge if k.get("mastery", 0) >= 4)
        learning = sum(1 for k in knowledge if 2 <= k.get("mastery", 0) < 4)
        new_items = sum(1 for k in knowledge if k.get("mastery", 0) <= 1)
        outdated = check_outdated(knowledge, 30)
        print(f"[STATUS] 知识星图学习状态 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"\n  总计: {total} | 已掌握: {mastered}({round(mastered/total*100)}%) | 学习中: {learning} | 未接触: {new_items}")
        print(f"\n  领域: " + " | ".join(f"{CAT_LABELS.get(c,c)}({n})" for c,n in sorted(cats.items(),key=lambda x:-x[1])))
        if outdated:
            print(f"\n  [R] {len(outdated)}个知识点超过30天未复习:")
            for k in outdated[:5]:
                print(f"    - {k['title']} ({k['days_ago']}天前)")
        recs = get_recommendations(knowledge)
        if recs:
            print(f"\n  >> 推荐下一步:")
            for i, rec in enumerate(recs[:3], 1):
                print(f"    {i}. {rec['title']} (掌握度:{rec.get('mastery',0)}/5)")

    elif args.recommend or args.recommend_path:
        recs = get_recommendations(knowledge)
        print("[PATH] 推荐学习路径：\n")
        for i, rec in enumerate(recs[:5], 1):
            mastery = rec.get("mastery", 0)
            status = "[DONE] 已完成" if mastery >= 3 else "[LEARNING] 学习中" if mastery >= 2 else "[TODO] 未开始"
            pre_status = "[OK] 前置已完成" if rec.get("pre_completed") else "[WAIT] 前置未完成"
            print(f"{i}. [{status}] {rec.get('title', '')}")
            print(f"   掌握度: {mastery}星 | {pre_status}")
            print(f"   摘要: {rec.get('summary', '')}\n")

    elif args.report:
        report = generate_report(knowledge)
        print(report)
        REPORT_PATH.write_text(report, encoding="utf-8")
        print(f"\n[SAVED] 报告已保存到: {REPORT_PATH}")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
