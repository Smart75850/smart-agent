# Claude Code 配置

## 知识星图自动教学系统

### 配置信息（跨平台 — Windows / Mac 共用同一份数据）
- 知识星图数据: `smart-agent/knowledge-star/knowledge-galaxy-data.json`（Git 同步）
- 知识星图 HTML: `~/Saved Games/knowledge-galaxy.html`（自动检测平台）
- 学习报告: `~/Saved Games/knowledge-report.md`
- **同步机制**: 数据源放 Git 仓库，脚本自动检测路径，Windows/Mac 共享同一份逻辑

### 自动教学规则

#### 1. 会话初始化
每次会话开始时，自动执行以下命令加载星图并推荐学习路径：
```bash
python C:/Users/guohu/.claude/skills/knowledge-tutor/scripts/match-knowledge.py --init
python C:/Users/guohu/.claude/skills/knowledge-tutor/scripts/match-knowledge.py --recommend
```

#### 2. 任务匹配
当用户提供任务或问题时，自动匹配相关知识点：
```bash
python C:/Users/guohu/.claude/skills/knowledge-tutor/scripts/match-knowledge.py --match "任务描述"
```

#### 3. 知识点展示
匹配到知识点后，按以下格式展示：
```
📚 相关知识参考：

【知识点标题】
- 摘要：xxx
- 掌握度：⭐⭐⭐⭐
- 相关项目：xxx

💡 要了解更多？输入「详细」查看完整内容。
```

#### 4. 学习进度更新
任务完成后，自动更新学习进度：
```bash
python C:/Users/guohu/.claude/skills/knowledge-tutor/scripts/match-knowledge.py --update <知识ID> --mastery +1
```

#### 5. 学习路径推荐
根据当前掌握度，推荐下一步学习：
```bash
python C:/Users/guohu/.claude/skills/knowledge-tutor/scripts/match-knowledge.py --recommend
```

#### 6. 周报生成
每周生成学习周报：
```bash
python C:/Users/guohu/.claude/skills/knowledge-tutor/scripts/match-knowledge.py --report
```

### 主动教学模式

当检测到以下情况时，主动提供教学：

1. **任务涉及未掌握的知识点**（mastery < 3）
2. **任务涉及高影响力知识点**（vc > 10）
3. **任务涉及相关依赖知识点**（pre 字段）

教学提示格式：
```
🎓 教学提示：

你正在处理的任务涉及「XXX」知识点。
该知识点的前置依赖是：[A, B, C]
建议先了解这些前置知识。

要我现在解释吗？
```

### IMA 知识库 × 知识星图 桥接系统

#### 架构概览
```
IMA 订阅库 (8个, 6万+条)
    ↓ search_knowledge
IMA-Galaxy Bridge (ima-galaxy-bridge.py)
    ↓ WebSearch找原文URL → import_urls
辉的知识库 (私人KB, 完整原文)
    ↓ get_media_info → 读全文 → 提取精华
知识星图 (knowledge-galaxy.html, 3D可视化)
```

#### 桥接脚本
- 脚本位置: `C:\Users\guohu\.claude\skills\knowledge-tutor\scripts\ima-galaxy-bridge.py`
- IMA 凭证: `~/.config/ima/client_id` + `~/.config/ima/api_key`

#### 命令速查
```bash
python ima-galaxy-bridge.py search "关键词"        # 搜索订阅库
python ima-galaxy-bridge.py fullcopy "关键词" -y    # 搜索+联网找原文+导入私人KB
python ima-galaxy-bridge.py batch "关键词" -y       # 批量导入星图
python ima-galaxy-bridge.py copy "关键词" -y        # 书签模式存入私人KB
python ima-galaxy-bridge.py stats                   # 查看状态
```

#### 完整工作流（Agent 自动化）
1. 用户讲「帮我从订阅库搜XX相关内容」
2. Agent 执行 `search` 命令 → 返回标题列表
3. Agent 判断有用 → 对每条用 `WebSearch` 搜标题 → 找到原文 URL
4. 调用 IMA `import_urls` API → 完整原文导入「辉的知识库」
5. 调用 `get_media_info` → 读取全文
6. 提取关键知识点 → 调用 `batch` 导入知识星图（3D可视化节点）

#### 已订阅知识库
| 知识库 | 内容数 |
|------|------|
| 前沿AI资讯【每日多次更新】 | 15,761 |
| ai相关超全知识库（持续更新）| 14,172 |
| 长安投研【持续更新】 | 41,533 |
| AI赋能教育教学创新 | 3,488 |
| 海易查 | 3,741 |
| AI Agent | 2,296 |
| AI提示词与智能体精品库 | 1,613 |
| ima知识库高级版Learnima | 1,029 |
| AI+副业 超级个体实战 | 344 |
| 1000个AI工具推荐 | 324 |
| #扣叔-新闻传播学 | 125 |
| 300个副业项目 | 113 |
| 闲鱼虚拟资料问答库 | 109 |
| AI生成各种指令（DeepSeek） | 21 |
| IMA第二大脑 | 22 |
| 辉的知识库 (私人) | 23 |

#### 权限边界
- **订阅库**: 可搜索标题/摘要，不可直接下载原文（错误码 220030）
- **私人库**: 完整权限（搜索/浏览/下载原文/上传/导入URL）
- **突破**: 用 `WebSearch` 联网找到原文 URL → `import_urls` 导入私人库

### Smart Fetch MCP（反爬 URL 抓取）

- 脚本: `C:\Users\guohu\workspace\smart-agent\src\mcp_tools\smart_fetch_server.py`
- 能力: curl_cffi TLS 指纹伪装 + 浏览器 UA → 突破反爬
- 已配置到 `settings.json` → `mcpServers.smart-fetch`
- 适用站点: 普通博客、技术文章站（知乎/CSDN 等强反爬需 Smart Agent 完整适配器）
- 工具: `smart_fetch(url, headers?, timeout?)` → 返回纯文本内容
- 自动 HTML→文本提取，8000 字上限防 token 爆炸

### 多 Agent 兼容

本配置支持以下 Agent：
- **Codex**: 读取 `~/.codex/skills/knowledge-tutor/`
- **Claude Code**: 读取 `~/.claude/skills/knowledge-tutor/`
- **Hermes**: 读取 `~/.hermes/skills/knowledge-tutor/`
- **Open Claw**: 读取 `~/.openclaw/skills/knowledge-tutor/`

所有 Agent 共享同一个知识星图文件，任何 Agent 的更新都会反映到所有 Agent。

### 会话启动铁律
- 星图数据: 自动检测路径（优先 Git 仓库 `smart-agent/knowledge-star/`）
- **只在涉及以下领域时**，主动引用知识星图并推荐学习路径：AI/Agent/视频逆向/多模态/提示词/安全/爬虫/内容分析
- 一般聊天、系统配置、吹水、调相 — 唔使 check 星图，唔好烧 token

### Mac 端同步

Mac 上 Claude Code 要同 Windows 共享知识，只需：

```bash
# 1. Clone smart-agent 仓库（如果未 clone）
git clone https://github.com/Smart75850/smart-agent.git ~/workspace/smart-agent

# 2. 复制 CLAUDE.md 同 skills 到 Mac Claude Code 目录
cp ~/workspace/smart-agent/knowledge-star/CLAUDE.md ~/.claude/CLAUDE.md
cp -r ~/workspace/smart-agent/knowledge-star/skills/ ~/.claude/skills/

# 3. 每次 git pull 更新
cd ~/workspace/smart-agent && git pull
```

**重要**: Mac Claude Code 会话开始时，会运行 `match-knowledge.py --init`，脚本会自动检测 Git 仓库中嘅知识星图数据。两边机共享同一份数据源。
