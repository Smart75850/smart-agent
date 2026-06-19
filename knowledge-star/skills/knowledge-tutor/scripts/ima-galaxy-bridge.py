#!/usr/bin/env python3
"""
IMA × 知识星图 桥接脚本
=======================
封装 IMA OpenAPI 搜索 + 联网补全原文URL + 导入私人知识库 + 星图节点生成。

用法:
  python ima-galaxy-bridge.py search "Claude Code"          # 搜索 IMA 订阅库
  python ima-galaxy-bridge.py fullcopy "Claude Code" -y      # 搜索→联网找原文→导入私人KB（完整原文）
  python ima-galaxy-bridge.py suggest "Claude Code"          # 搜索并生成星图节点建议
  python ima-galaxy-bridge.py batch "MCP" --max 10           # 批量导入星图
  python ima-galaxy-bridge.py copy "关键词" -y                # 书签模式存入私人KB
  python ima-galaxy-bridge.py stats                          # 查看当前状态

完整工作流（AI Agent 自动化）:
  订阅库搜索 → AI筛选 → WebSearch找原文URL → import_urls导入私人KB
  → get_media_info读全文 → 提取精华 → 生成星图节点
"""

import os
import sys
import json
import argparse
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Windows GBK 终端兼容
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except:
        pass

# --- 配置 ---
BASE_URL = "https://ima.qq.com"
KNOWLEDGE_BASE_ID = "NasLUJGJSRl5gLkaNTb8LDgPmAMuR1DU6gSjM_m5d0I="  # Learnima
def _find_galaxy_data() -> Path:
    """跨平台自动检测知识星图数据文件。"""
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent.parent / "workspace" / "smart-agent" / "knowledge-star" / "knowledge-galaxy-data.json",
        Path(os.environ.get("USERPROFILE", "")) / "Saved Games" / "knowledge-galaxy-data.json",
        Path.home() / "Saved Games" / "knowledge-galaxy-data.json",
        Path.home() / ".claude" / "knowledge-star" / "knowledge-galaxy-data.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]

GALAXY_JSON = _find_galaxy_data()
GALAXY_HTML = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Saved Games" / "knowledge-galaxy.html"
# fallback if Windows path doesn't exist
if not GALAXY_HTML.exists():
    GALAXY_HTML = Path.home() / "Saved Games" / "knowledge-galaxy.html"
CRED_DIR = Path.home() / ".config/ima"

# 星图领域映射：IMA 内容关键词 → 星图 cat
CAT_MAP = {
    "ai": ["AI", "Agent", "LLM", "大模型", "GPT", "Claude", "DeepSeek", "深度学习",
           "Transformer", "BERT", "Prompt", "RAG", "多模态", "MCP", "n8n", "智能体",
           "机器学习", "神经网络", "NLP", "CV", "GNN", "RL"],
    "python": ["Python", "FastAPI", "Django", "Flask", "httpx", "pytest",
               "Docker", "PostgreSQL", "SQL", "Redis", "异步", "爬虫", "CDP"],
    "product": ["产品", "变现", "运营", "增长", "SEO", "用户体验", "商业模式",
                "SaaS", "开源", "订阅", "营销", "写作", "内容创作", "ima"],
    "reverse": ["逆向", "TLS", "指纹", "签名", "Cookie", "验证码", "反爬",
                "CDP", "Playwright", "Selenium", "抢购", "秒杀"],
    "frontend": ["React", "Vue", "Next.js", "TypeScript", "CSS", "Canvas",
                 "前端", "Tailwind", "JavaScript", "HTML"],
    "ima_sub": ["ima", "IMA", "知识库", "订阅", "知识星图", "第二大脑",
                "超级个体", "知识管理", "Claw"],
}

# --- 凭证 ---
def load_credentials():
    client_id = api_key = ""
    if CRED_DIR.exists():
        client_id = (CRED_DIR / "client_id").read_text().strip()
        api_key = (CRED_DIR / "api_key").read_text().strip()
    client_id = os.environ.get("IMA_OPENAPI_CLIENTID") or client_id
    api_key = os.environ.get("IMA_OPENAPI_APIKEY") or api_key
    if not client_id or not api_key:
        print("[ERROR] 未找到 IMA 凭证。请设置环境变量或 ~/.config/ima/")
        sys.exit(1)
    return client_id, api_key

# --- IMA API ---
def ima_api(path, body, timeout=15):
    import urllib.request
    import urllib.error
    client_id, api_key = load_credentials()
    url = f"{BASE_URL}{path}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("ima-openapi-clientid", client_id)
    req.add_header("ima-openapi-apikey", api_key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"code": -1, "msg": f"HTTP {e.code}", "data": {}}
    except Exception as e:
        return {"code": -1, "msg": str(e), "data": {}}

def search_knowledge(query, kb_id=KNOWLEDGE_BASE_ID, cursor=""):
    """搜索知识库内容"""
    return ima_api("/openapi/wiki/v1/search_knowledge", {
        "query": query,
        "knowledge_base_id": kb_id,
        "cursor": cursor,
    })

def get_media_info(media_id):
    """获取媒体详情"""
    return ima_api("/openapi/wiki/v1/get_media_info", {"media_id": media_id})

def list_knowledge_bases():
    """列出所有可访问知识库"""
    return ima_api("/openapi/wiki/v1/search_knowledge_base", {
        "query": "", "cursor": "", "limit": 20
    })

# --- 领域推断 ---
def infer_category(title, summary=""):
    """根据标题和摘要推断星图领域"""
    text = f"{title} {summary}"
    scores = {}
    for cat, keywords in CAT_MAP.items():
        score = 0
        for kw in keywords:
            if kw.lower() in text.lower():
                score += 1
        if score > 0:
            scores[cat] = score
    if not scores:
        return "ai"  # 默认 AI
    return max(scores, key=scores.get)

# --- 星图节点生成 ---
def build_node(ima_item, next_id=None):
    """将 IMA 搜索结果转为星图节点"""
    if next_id is None:
        next_id = get_max_id() + 1

    title = ima_item.get("title", "未命名")
    cat = infer_category(title, ima_item.get("highlight_content", ""))
    media_id = ima_item.get("media_id", "")

    # 生成短 ID（用于去重）
    short_id = hashlib.md5(media_id.encode()).hexdigest()[:8]

    # 摘要：用高亮内容或截取标题
    summary = ima_item.get("highlight_content", "")
    if not summary:
        summary = f"来自 IMA Learnima 知识库：{title[:60]}"

    # vc 基于标题丰富度估算
    vc = min(8, max(1, len(title) // 10 + len(summary) // 50))

    node = {
        "id": next_id,
        "title": title[:80],
        "summary": summary[:120],
        "content": f"IMA Learnima 订阅知识库 · {title}\nmedia_id: {media_id}\n领域: {cat}\n原始链接需通过 get_media_info 获取。",
        "cat": cat,
        "rel": [],
        "pre": [],
        "proj": [],
        "mastery": 2,
        "vc": vc,
        "lv": datetime.now().strftime("%Y-%m-%d"),
        "ca": datetime.now().strftime("%Y-%m-%d"),
        "_ima_media_id": media_id,
        "_ima_short_id": short_id,
    }
    return node

# --- 星图 HTML 读写 ---
def read_galaxy_data():
    """从 HTML 提取所有节点对象（用 ast.literal_eval 兼容 JS 格式）"""
    import re
    content = GALAXY_HTML.read_text(encoding="utf-8")
    start_marker = "const DEFAULT_DATA = ["
    end_marker = "]\n\n// ===="
    start = content.find(start_marker)
    end = content.find(end_marker, start)
    if start == -1 or end == -1:
        raise ValueError("找不到 DEFAULT_DATA 在 HTML 中")
    block = content[start + len(start_marker):end]
    # 提取每个 {id:...} 对象
    nodes = []
    depth = 0
    buf = ""
    in_obj = False
    for ch in block:
        if ch == '{' and not in_obj:
            in_obj = True
            depth = 0
            buf = ""
        if in_obj:
            buf += ch
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    nodes.append(buf)
                    in_obj = False
    return nodes

def get_max_id():
    content = GALAXY_HTML.read_text(encoding="utf-8")
    import re
    ids = re.findall(r'\{id:(\d+),', content)
    return max(int(i) for i in ids) if ids else 67

def format_node_js(node):
    """将 Python dict 格式化为 JS 对象字面量"""
    parts = []
    parts.append(f"id:{node['id']}")
    parts.append(f"title:{json.dumps(node['title'], ensure_ascii=False)}")
    parts.append(f"summary:{json.dumps(node.get('summary',''), ensure_ascii=False)}")
    parts.append(f"content:{json.dumps(node.get('content',''), ensure_ascii=False)}")
    parts.append(f"cat:{json.dumps(node.get('cat','ai'))}")
    rel = node.get('rel', [])
    parts.append(f"rel:{json.dumps(rel)}")
    pre = node.get('pre', [])
    parts.append(f"pre:{json.dumps(pre)}")
    proj = node.get('proj', [])
    parts.append(f"proj:{json.dumps(proj)}")
    parts.append(f"mastery:{node.get('mastery',2)},vc:{node.get('vc',1)}")
    parts.append(f"lv:{json.dumps(node.get('lv','2026-06-06'))}")
    parts.append(f"ca:{json.dumps(node.get('ca','2026-06-06'))}")
    ima_mid = node.get('_ima_media_id', '')
    if ima_mid:
        parts.append(f"_ima_media_id:{json.dumps(ima_mid)}")
    return "{" + ",".join(parts) + "}"

def write_galaxy_data(nodes_js_strings):
    """将 JS 对象字符串追加到 DEFAULT_DATA 末尾"""
    content = GALAXY_HTML.read_text(encoding="utf-8")
    end_marker = "]\n\n// ===="
    end_pos = content.find(end_marker)
    if end_pos == -1:
        raise ValueError("找不到 DEFAULT_DATA 尾部")
    # 在 ]; 之前插入新节点
    new_block = ",\n  ".join(nodes_js_strings)
    # 检查最后一个节点後面是否有逗号
    insert_pos = end_pos
    new_content = content[:insert_pos] + ",\n  " + new_block + content[insert_pos:]
    GALAXY_HTML.write_text(new_content, encoding="utf-8")
    return True

# --- 命令 ---
def cmd_search(args):
    """搜索 IMA 知识库"""
    print(f"🔍 在 Learnima 搜索: {args.query}")
    result = search_knowledge(args.query)
    if result.get("code") != 0:
        print(f"  [ERROR] {result.get('msg', '未知错误')}")
        return
    items = result.get("data", {}).get("info_list", [])
    print(f"  共 {len(items)} 条结果\n")
    for i, item in enumerate(items[:args.max], 1):
        cat = infer_category(item.get("title", ""), item.get("highlight_content", ""))
        print(f"  {i}. [{cat}] {item.get('title', '无标题')}")
        media_id = item.get("media_id", "")
        print(f"     media_id: {media_id}")
        hl = item.get("highlight_content", "")
        if hl:
            print(f"     摘要: {hl[:100]}...")
        print()

def cmd_suggest(args):
    """搜索并生成星图节点建议"""
    print(f"🔍 搜索: {args.query}")
    result = search_knowledge(args.query)
    if result.get("code") != 0:
        print(f"  [ERROR] {result.get('msg')}")
        return
    items = result.get("data", {}).get("info_list", [])
    max_id = get_max_id()
    print(f"  共 {len(items)} 条，生成节点建议:\n")
    suggestions = []
    for i, item in enumerate(items[:args.max], 1):
        node = build_node(item, max_id + i)
        suggestions.append(node)
        print(f"  [{node['cat']}] {node['title']}")
        print(f"  vc={node['vc']} mastery={node['mastery']} id={node['id']}")
        print()

    # 输出 JSON（方便程序处理）
    if args.json:
        print("\n--- JSON ---")
        print(json.dumps(suggestions, ensure_ascii=False, indent=2))

def cmd_import(args):
    """将单篇文章导入星图"""
    # 先获取文章信息
    result = get_media_info(args.media_id)
    if result.get("code") != 0:
        print(f"[ERROR] {result.get('msg', '无法获取文章信息')}")
        return

    # 尝试搜索找到标题
    # 用 media_id 构建节点
    data = result.get("data", {})
    title = args.title or f"IMA文章_{args.media_id[:12]}"
    summary = args.summary or "来自 IMA Learnima"

    max_id = get_max_id()
    node = build_node({
        "title": title,
        "media_id": args.media_id,
        "highlight_content": summary,
    }, max_id + 1)

    # 格式化为 JS 并追加到星图
    js_str = format_node_js(node)
    write_galaxy_data([js_str])
    print(f"已导入: [{node['cat']}] {node['title']} (id={node['id']})")

def cmd_batch(args):
    """批量搜索并导入"""
    print(f"🔍 批量导入: {args.query}")
    result = search_knowledge(args.query)
    if result.get("code") != 0:
        print(f"[ERROR] {result.get('msg')}")
        return
    items = result.get("data", {}).get("info_list", [])[:args.max]
    if not items:
        print("  无结果")
        return

    # 显示候选
    print(f"  将导入 {len(items)} 条:\n")
    max_id = get_max_id()
    new_nodes = []
    for i, item in enumerate(items, 1):
        node = build_node(item, max_id + i)
        new_nodes.append(node)
        print(f"  {i}. [{node['cat']}] {node['title']}")

    # 确认
    if not args.yes:
        resp = input("\n确认导入? [y/N]: ").strip().lower()
        if resp != 'y':
            print("已取消")
            return

    existing_js_strs = read_galaxy_data()
    new_js_strs = [format_node_js(n) for n in new_nodes]
    existing_js_strs.extend(new_js_strs)
    # 重建完整数据
    content = GALAXY_HTML.read_text(encoding="utf-8")
    start_marker = "const DEFAULT_DATA = ["
    end_marker = "]\n\n// ===="
    start = content.find(start_marker)
    end = content.find(end_marker, start)
    all_block = ",\n  ".join(existing_js_strs)
    new_content = content[:start] + "const DEFAULT_DATA = [\n  " + all_block + content[end:]
    GALAXY_HTML.write_text(new_content, encoding="utf-8")
    print(f"\n已导入 {len(new_nodes)} 条到知识星图")

def cmd_copy(args):
    """搜索订阅库 + 智能分类 + 创建书签笔记 + 加入自己知识库"""
    OWN_KB_ID = "LEvdXdMzs5Vwbk8qhXD7l-quqSCpA9txUP7tmxVkIXg="

    # 文件类型：冇外部链接，只能书签
    FILE_TYPES = {1: "PDF", 3: "Word", 4: "PPT", 5: "Excel", 7: "Markdown",
                  9: "图片", 13: "TXT", 15: "录音"}
    # 网页类型：可以联网找原文 URL
    WEB_TYPES = {2: "网页", 6: "微信公众号"}

    print(f"搜索订阅库: {args.query}")
    result = search_knowledge(args.query, kb_id=KNOWLEDGE_BASE_ID)
    if result.get("code") != 0:
        print(f"  [ERROR] {result.get('msg')}")
        return
    items = result.get("data", {}).get("info_list", [])[:args.max]
    if not items:
        print("  无结果")
        return

    # 分类展示
    web_items, file_items, note_items = [], [], []
    for item in items:
        mt = item.get("media_type", 0)
        if mt in WEB_TYPES:
            web_items.append(item)
        elif mt in FILE_TYPES:
            file_items.append(item)
        else:
            note_items.append(item)

    print(f"  网页文章: {len(web_items)} 篇 (可联网找原文URL → 导入完整原文)")
    for i, item in enumerate(web_items, 1):
        print(f"    {i}. [{WEB_TYPES[item['media_type']]}] {item.get('title','')[:60]}")
    print(f"  文件类: {len(file_items)} 篇 (PDF/Word等，只能书签)")
    for i, item in enumerate(file_items, 1):
        print(f"    {i}. [{FILE_TYPES[item['media_type']]}] {item.get('title','')[:60]}")
    print(f"  其他: {len(note_items)} 篇")

    if not args.yes:
        resp = input("\n确认存入「辉的知识库」? [y/N]: ").strip().lower()
        if resp != 'y':
            print("已取消")
            return

    success = 0
    for item in items:
        title = item.get("title", "未命名")
        mt = item.get("media_type", 0)
        hl = item.get("highlight_content", "")
        type_label = WEB_TYPES.get(mt) or FILE_TYPES.get(mt) or f"类型{mt}"

        md = f"# {title}\n\n**来源**: ima知识库高级版Learnima (订阅库)\n**类型**: {type_label}\n**收录**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n{hl[:300]}"
        note_r = ima_api("/openapi/note/v1/import_doc", {
            "content_format": 1, "content": md, "folder_name": "IMA书签"
        })
        if note_r.get("code") != 0:
            print(f"  [失败] {title[:40]}: {note_r.get('msg')}")
            continue
        note_id = note_r["data"]["note_id"]
        add_r = ima_api("/openapi/wiki/v1/add_knowledge", {
            "media_type": 11, "note_info": {"content_id": note_id},
            "title": title[:80], "knowledge_base_id": OWN_KB_ID,
        })
        if add_r.get("code") == 0:
            success += 1
            print(f"  [OK] [{type_label}] {title[:50]}")
        else:
            print(f"  [失败] {title[:40]}: {add_r.get('msg')}")
    print(f"\n  完成: {success}/{len(items)} 条已存入「辉的知识库」")
    if web_items:
        print(f"  💡 {len(web_items)} 篇网页文章可进一步用 WebSearch 找原文 URL 导入完整原文")

def cmd_fullcopy(args):
    """
    搜索订阅库 → 联网找原文URL → 导入私人KB（完整原文）
    这是推荐的完整工作流：最终拿到的是完整原文，不是书签。
    需要 WebSearch 工具支持（Agent 自动调用）。
    """
    OWN_KB_ID = "LEvdXdMzs5Vwbk8qhXD7l-quqSCpA9txUP7tmxVkIXg="

    print(f"[1/3] 搜索订阅库: {args.query}")
    result = search_knowledge(args.query, kb_id=KNOWLEDGE_BASE_ID)
    if result.get("code") != 0:
        print(f"  [ERROR] {result.get('msg')}")
        return
    items = result.get("data", {}).get("info_list", [])[:args.max]
    if not items:
        print("  无结果")
        return

    print(f"  找到 {len(items)} 条")
    print(f"\n[2/3] 需要 AI Agent 辅助：对每条结果用 WebSearch 搜标题 → 找原文 URL → import_urls 导入私人 KB")
    print(f"  (此步骤依赖 Claude Code 的 WebSearch 工具，请用 AI Agent 执行)\n")

    # 输出结构化数据供 Agent 使用
    output = {
        "action": "fullcopy",
        "target_kb": OWN_KB_ID,
        "items": []
    }
    for item in items:
        output["items"].append({
            "title": item.get("title", ""),
            "media_id": item.get("media_id", ""),
            "media_type": item.get("media_type", 0),
            "search_query": f"{item.get('title', '')} {'知乎' if '知乎' in item.get('title','') else ''}",
        })
    print(json.dumps(output, ensure_ascii=False, indent=2))

def cmd_stats(args):
    """显示当前状态"""
    client_id, _ = load_credentials()

    # IMA 状态
    print("═══ IMA 知识库 ═══")
    kb_result = list_knowledge_bases()
    if kb_result.get("code") == 0:
        for kb in kb_result.get("data", {}).get("info_list", []):
            print(f"  📚 {kb.get('kb_name', '?')} | {kb.get('content_count', 0)} 条 | {kb.get('base_type', '?')}")

    # 星图状态
    print("\n═══ 知识星图 ═══")
    try:
        nodes_js = read_galaxy_data()
        ima_count = sum(1 for n in nodes_js if '_ima_media_id' in n)
        print(f"  总节点: {len(nodes_js)}")
        print(f"  IMA 来源: {ima_count}")
    except Exception as e:
        print(f"  [ERROR] 读取星图失败: {e}")

    print(f"\n  凭证: {'✅' if client_id else '❌'}")

def cmd_health(args):
    """健康检查"""
    print("═══ Bridge 健康检查 ═══\n")
    # 凭证
    try:
        cid, key = load_credentials()
        print(f"  凭证: ✅ (ID={cid[:8]}...)")
    except:
        print(f"  凭证: ❌")
        return

    # IMA API
    r = ima_api("/openapi/wiki/v1/search_knowledge_base", {"query":"","cursor":"","limit":1})
    print(f"  IMA API: {'✅' if r.get('code')==0 else '❌ '+r.get('msg','')}")

    # 星图
    try:
        nodes_js = read_galaxy_data()
        print(f"  星图: 可用 ({len(nodes_js)} 节点)")
    except:
        print(f"  星图: 不可读取")

    print("\n  ✅ 全部正常" if r.get('code')==0 else "\n  ⚠️ 有问题")

# --- CLI ---
def main():
    parser = argparse.ArgumentParser(description="IMA × 知识星图 桥接脚本")
    sub = parser.add_subparsers(dest="cmd")

    p_search = sub.add_parser("search", help="搜索 IMA 知识库")
    p_search.add_argument("query", help="搜索关键词")
    p_search.add_argument("--max", type=int, default=10, help="最大结果数")

    p_suggest = sub.add_parser("suggest", help="搜索并生成星图节点建议")
    p_suggest.add_argument("query", help="搜索关键词")
    p_suggest.add_argument("--max", type=int, default=10)
    p_suggest.add_argument("--json", action="store_true", help="输出 JSON")

    p_import = sub.add_parser("import", help="导入单篇到星图")
    p_import.add_argument("media_id", help="IMA media_id")
    p_import.add_argument("--title", help="节点标题（默认用 IMA 标题）")
    p_import.add_argument("--summary", help="节点摘要")

    p_batch = sub.add_parser("batch", help="批量搜索并导入星图")
    p_batch.add_argument("query", help="搜索关键词")
    p_batch.add_argument("--max", type=int, default=10)
    p_batch.add_argument("--yes", "-y", action="store_true", help="跳过确认")

    p_fullcopy = sub.add_parser("fullcopy", help="搜索+联网找原文+导入私人KB（完整原文）")
    p_fullcopy.add_argument("query", help="搜索关键词")
    p_fullcopy.add_argument("--max", type=int, default=10)
    p_fullcopy.add_argument("--yes", "-y", action="store_true")

    p_copy = sub.add_parser("copy", help="搜索订阅库并存入自己知识库（书签模式）")
    p_copy.add_argument("query", help="搜索关键词")
    p_copy.add_argument("--max", type=int, default=10)
    p_copy.add_argument("--yes", "-y", action="store_true", help="跳过确认")

    p_stats = sub.add_parser("stats", help="查看状态")
    p_health = sub.add_parser("health", help="健康检查")

    args = parser.parse_args()
    if args.cmd == "search":
        cmd_search(args)
    elif args.cmd == "suggest":
        cmd_suggest(args)
    elif args.cmd == "import":
        cmd_import(args)
    elif args.cmd == "batch":
        cmd_batch(args)
    elif args.cmd == "copy":
        cmd_copy(args)
    elif args.cmd == "fullcopy":
        cmd_fullcopy(args)
    elif args.cmd == "stats":
        cmd_stats(args)
    elif args.cmd == "health":
        cmd_health(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
