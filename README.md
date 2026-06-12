# Smart Agent — 多平台 AI 内容分析引擎

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)]()  
[![License](https://img.shields.io/badge/License-MIT-green)]()  
[![Platform](https://img.shields.io/badge/Platform-7平台-orange)]()

> ⚠️ 本项目仅供学习与学术研究使用，严禁用于商业用途。[详细免责声明](DISCLAIMER.md)

---

## 一句话介绍

**输入一个关键词，自动搜索知乎/B站/小红书/抖音等 7 个平台，7 个 AI Agent 并联分析爆款趋势、竞品策略、用户情绪，输出结构化报告。**

---

## 快速开始

```bash
git clone https://github.com/Smart75850/smart-agent.git
cd smart-agent
pip install -r requirements.txt

# 单平台搜索
python main.py --platform bilibili --keyword "AI工具"

# 全平台并发搜索 + AI 全链路分析
python main.py --platform all --keyword "一人公司" --type aggregate --engine langgraph --pipeline full

# MCP Server 模式（推荐）
python -m src.mcp_tools.server
```

> 📖 完整指南：[docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md)

---

## 核心能力

### 数据采集层

| 平台 | 搜索 | 热榜 | 详情 | 评论 | 用户 | 方式 |
|------|:---:|:---:|:---:|:---:|:---:|------|
| B站 | ✅ | ✅ | ✅ | ✅ | ✅ | 纯 HTTP |
| 小红书 | ✅ | ✅ | ✅ | ✅ | ✅ | CDP 浏览器 |
| 抖音 | ✅ | ✅ | ✅ | ✅ | ✅ | CDP 浏览器 |
| 知乎 | ✅ | ✅ | ✅ | ✅ | ✅ | 纯 HTTP |
| 快手 | ✅ | ✅ | ✅ | ✅ | ✅ | 纯 HTTP |
| 微博 | ✅ | ✅ | ✅ | ✅ | ✅ | 纯 HTTP |
| 贴吧 | ✅ | ✅ | ✅ | ✅ | ✅ | 纯 HTTP |

- 三层反爬引擎：Light(HTTP+TLS) / Stealth(浏览器+Cloudflare) / Smart(自动选择)
- 断点续跑 + 去重 + 6 种存储后端（JSON/CSV/Excel/SQLite/MySQL/JSONL）
- Camoufox C++ 反检测浏览器引擎

### AI 分析层 — 7 个专业 Agent

| Agent | 功能 | 典型输出 |
|------|------|------|
| **TrendScout** | 爆款识别与趋势分析 | 爆款评分、趋势周期、传播路径 |
| **ProductMiner** | 产品/竞品深度分析 | 变现潜力、竞争优势、用户痛点 |
| **VideoAnalyst** | 视频结构拆解 | 钩子类型、节奏分析、结构模板 |
| **SentimentReader** | 评论情绪分析 | 正面/中性/负面比例、关键洞察 |
| **CopyWriter** | 营销文案生成 | 标题/短文案/中长篇/长文四档 |
| **ContentRemixer** | 内容改写与破圈检测 | 跨平台信号、改写建议 |
| **PicTactic** | 智能配图策略 | 封面/社交/趋势三类配图方案 |

> 每个 Agent 内置 CriticAgent 自修正 — review-retry loop，输出质量把关。  
> 无 API Key 时自动降级为模板模式，零成本可用。

### 编排与交付

- **LangGraph StateGraph DAG** — 多平台并行搜索 + 7 Agent 线性链
- **MCP Server** — 30+ 工具，Claude Desktop / Cursor / Hermes 原生调用
- **Go 二进制** — 9.4MB 单文件，Windows 即开即用
- **WebUI** — FastAPI + WebSocket 实时仪表板
- **Docker 一键部署**

---

## MCP Server — 用自然语言调度

```json
// Claude Desktop 配置
{
  "mcpServers": {
    "smart-agent": {
      "command": "python",
      "args": ["-m", "src.mcp_tools.server"]
    }
  }
}
```

配置后在 Claude Desktop / Hermes 中直接对话：

| 你说 | Agent 自动调用 |
|------|------|
| 「帮我搜知乎 AI Agent 话题」 | `zhihu_search_tool` |
| 「分析下 B站 这个视频的评论情绪」 | `bilibili_comment_tool` |
| 「对比抖音和快手同话题热度」 | `douyin_search_tool` + `kuaishou_search_tool` |
| 「帮我写一篇小红书种草文案」 | `xiaohongshu_search_tool` + CopyWriter |

---

## 技术栈

- Python 3.12+ · LangGraph · FastMCP · Playwright · Scrapling
- DeepSeek V4 API（LLM 驱动全部分析）
- Go 9.4MB 二进制（Windows 零依赖部署）
- Docker + Windows 一键部署脚本

---

## 与同类项目对比

| 维度 | MediaCrawler | Smart Agent |
|------|:--:|:--:|
| 平台数 | 7+ | 7 |
| 纯 HTTP | ✅ | ✅ |
| AI 分析 Agent | ❌ | ✅ 7 Agent |
| 自修正 Critic | ❌ | ✅ |
| MCP 协议 | ❌ | ✅ |
| Go 二进制 | ❌ | ✅ |
| 开源协议 | MIT | MIT |

---

## 项目结构

```
src/
├── agents/          # 7 平台 Adapter
├── orchestrator/    # LangGraph DAG + 7 Agent
│   └── agents/      # TrendScout / ProductMiner / SentimentReader / ...
├── mcp_tools/       # MCP Server
├── utils/           # 浏览器 / 反爬 / 日志 / Cookie / Session 管理
└── store/           # 6 种存储后端

go/                  # Go 高性能版本（6.7MB 二进制）
api/                 # WebUI 仪表板
```

---

## 路线图

- [x] 7 平台搜索
- [x] 7 Agent AI 分析
- [x] LangGraph DAG 编排
- [x] MCP Server
- [x] Go 高性能版本
- [x] Docker + Windows 部署
- [ ] 获客引擎（购买意图识别 + 获客文案生成）→ Pro 版
- [ ] 更多平台支持

---

## Pro 版

如需企业级功能（多账号 IP 池、自愈引擎、策略记忆、获客引擎、CookieBridge），请查看 [Smart Agent Pro](https://github.com/Smart75850/smart-agent-pro)（私人仓库，联系作者获取访问权限）。

---

## 作者

**Smart75850** — 独立开发者，All in AI Agent。

- GitHub: [@Smart75850](https://github.com/Smart75850)

---

## License

MIT License — 详见 [LICENSE](LICENSE)

---

⭐ 如果这个项目对你有帮助，请给一个 Star！
