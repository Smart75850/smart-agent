# Smart Agent

多平台内容采集框架 — 5 平台纯 HTTP 直连 + 7 平台全浏览器支持。

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)]()
[![License](https://img.shields.io/badge/License-NonCommercial-blue)]()
[![Platform](https://img.shields.io/badge/Platform-7平台-orange)]()

⚠️ 本项目仅供学习与学术研究使用，严禁用于商业用途。[详细免责声明](DISCLAIMER.md)

## 核心优势

- **纯 HTTP 直连** — 5 个平台（B站/知乎/快手/微博/贴吧）实现纯HTTP采集
- **浏览器 CDP 兜底** — 抖音/小红书走 CDP 浏览器模式，双路径容错不中断
- **会话自动管理** — 过期自动收割，无需手动维护
- **6 种存储后端** — JSON / CSV / JSONL / Excel / SQLite / MySQL
- **开箱即用** — Docker 部署 / WebUI 仪表板 / MCP Server 协议接口

## 平台支持

| 平台 | 搜索 | 热榜 | 详情 | 评论 | 用户 | 采集方式 | 说明 |
|------|:---:|:---:|:---:|:---:|:---:|:---:|------|
| B站 | ✅ | ✅ | — | ✅ | — | 纯HTTP | Wbi hashlib，无需登录 |
| 小红书 | ✅ | — | ✅ | ✅ | — | 浏览器 | CDP Chrome 真浏览器 |
| 抖音 | ✅ | — | ✅ | ✅ | ✅ | 浏览器 | CDP Chrome 真浏览器 |
| 知乎 | ✅ | ✅ | ✅ | ✅ | ✅ | 纯HTTP | curl_cffi + cookies |
| 快手 | ✅ | ✅ | — | — | — | 纯HTTP | 纯 cookies，零签名 |
| 微博 | ✅ | ✅ | ✅ | ✅ | ✅ | 纯HTTP | cookies + xsrf-token |
| 贴吧 | ✅ | ✅ | ✅ | ✅ | ✅ | 纯HTTP | curl_cffi Chrome TLS |

## 快速开始

### 安装

```bash
git clone https://github.com/Smart75850/smart-agent.git
cd smart-agent
pip install -r requirements.txt
playwright install chromium
```

### 30 秒上手

```bash
# B站搜索（无需登录，即开即用）
python main.py --platform bilibili --keyword Python

# 全平台并发搜索
python main.py --platform all --keyword 美食

# 知乎热榜
python main.py --platform zhihu --type hot

# 输出 CSV
set STORE_BACKEND=csv
python main.py --platform bilibili --keyword Python
```

### 纯 HTTP 模式（推荐，零浏览器）

大部分平台首次使用前需要从浏览器收割一次会话：

```bash
# 1. 打开已登录的 Chrome（CDP 模式）
chrome --remote-debugging-port=9222

# 2. 收割全部平台会话（一次性操作）
python -c "import asyncio; from src.utils.session_manager import harvest_all; asyncio.run(harvest_all())"

# 3. 之后即可纯 HTTP 直连，无需浏览器
python main.py --platform all --keyword 美食
```

会话文件保存在 `browser_data/{platform}_http_session.json`，收割一次可用数天。

### 会话自动管理

系统会自动检测会话是否过期，过期则自动从 CDP Chrome 重新收割：

```python
from src.utils.session_manager import ensure_session, check_health

# 检测会话健康状态
healthy = await check_health("weibo")

# 确保会话有效（过期自动收割）
await ensure_session("weibo")
```

### 代理池

编辑 `config/proxies.json` 填入代理地址：

```json
{
    "proxies": [
        "http://user:pass@proxy1.example.com:8080",
        "socks5://127.0.0.1:1080"
    ]
}
```

支持 HTTP/HTTPS/SOCKS5 代理，自动轮转 + 健康检测 + 失败剔除。

### WebUI 仪表板

```bash
python -m api.main
# → http://localhost:8000
```

内建暗色主题，WebSocket 实时日志，JSON/CSV 下载，任务轮询。

## CLI 参数

| 参数 | 说明 | 可选值 |
|------|------|------|
| `--platform` | 目标平台 | bilibili / xiaohongshu / douyin / zhihu / kuaishou / weibo / tieba / all |
| `--type` | 操作类型 | search / hot / detail / comment / user |
| `--keyword` | 搜索关键词 | 任意文本 |
| `--limit` | 结果数量 | 默认 20 |
| `--output` | 输出目录 | 默认 output/ |
| `--dry-run` | 预览执行计划 | — |
| `--list-platforms` | 列出支持平台 | — |

## 项目结构

```
smart-agent/
├── main.py                        # CLI 入口
├── api/                           # WebUI（FastAPI + SPA）
├── config/
│   ├── settings.py                # 集中配置
│   └── proxies.json               # 代理池配置
├── base/
│   └── platform_base.py           # PlatformAdapter 抽象基类
├── src/
│   ├── agents/                    # 7 平台适配器
│   │   ├── bilibili_adapter.py    # B站 — 纯 Python Wbi
│   │   ├── xiaohongshu_adapter.py # 小红书 — x-s 会话复用
│   │   ├── douyin_adapter.py      # 抖音 — 会话上下文
│   │   ├── zhihu_adapter.py       # 知乎 — 纯 cookies
│   │   ├── kuaishou_adapter.py    # 快手 — 纯 cookies
│   │   ├── weibo_adapter.py       # 微博 — cookies + xsrf
│   │   └── tieba_adapter.py       # 贴吧 — curl_cffi TLS
│   └── utils/
│       ├── ks_http.py             # 快手纯 HTTP 客户端
│       ├── zh_http.py             # 知乎纯 HTTP 客户端
│       ├── weibo_http.py          # 微博纯 HTTP 客户端
│       ├── tieba_http.py          # 贴吧纯 HTTP 客户端
│       ├── session_manager.py     # 会话健康检测 + 自动收割
│       ├── proxy_pool.py          # 代理池轮转 + 健康检测
│       ├── browser_service.py     # CDP 浏览器控制
│       └── logger.py              # 统一日志
├── store/                         # 6 种存储后端
├── browser_data/                  # 会话收割文件
├── output/                        # 默认输出目录
└── docs/
    └── 使用指南.md                 # 详细使用文档
```

## 扩展功能

本仓库同时包含以下可直接使用的扩展模块：

- **MCP Server** — 标准 MCP 协议接口（25 个工具），可接入 Claude Desktop / Cursor 等 AI 工具链
- **Docker 部署** — `docker compose up` 即开即用
- **断点续爬 + 去重** — SQLite 持久化，中断后自动续传，支持 `--resume`
- **AI Agent 管线** — LangGraph + DeepSeek LLM 驱动，9 个分析 Agent（趋势/选品/视频/情绪/文案/配图等）
- **批量下载器** — 视频 + 封面图批量下载
- **Go 高性能模式** — Go 二进制（6.7MB）替代 Python CLI，并发性能提升 5-10 倍

## 免责声明

本项目仅供个人学习与学术研究使用。详见 [完整免责声明](DISCLAIMER.md)。

## License

NON-COMMERCIAL LEARNING LICENSE 1.0
