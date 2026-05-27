<div align="center">

# Smart Agent

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)]()
[![License](https://img.shields.io/badge/License-NonCommercial-blue)]()
[![CI](https://github.com/Smart75850/smart-agent/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Smart75850/smart-agent/actions/workflows/ci.yml)
[![Platform](https://img.shields.io/badge/Platform-B站%20|%20小紅書%20|%20抖音%20|%20知乎%20|%20快手-orange)]()

多平台內容採集框架 — 純爬蟲，輸出結構化數據

</div>

⚠️⚠️⚠️⚠️ **请以学习为目的使用本仓库，严禁用于商业用途。** [详细免责声明](DISCLAIMER.md)

## 功能特性

| 功能 | B站 | 小紅書 | 抖音 | 知乎 | 快手 |
|------|:---:|:-----:|:---:|:---:|:---:|
| 關鍵字搜索 | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| 排行榜/熱榜 | ✅ | — | — | ✅ | ⚠️ |
| 筆記詳情 | — | ✅ | — | — | — |
| 用戶作品 | — | — | ✅ | — | — |
| 評論爬取 | ✅ | ✅ | ✅ | ✅ | — |
| CDP 登入 | ❌ | ✅ | ✅ | ✅ | ✅ |
| JSON 輸出 | ✅ | ✅ | ✅ | ✅ | ✅ |
| CSV 輸出 | ✅ | ✅ | ✅ | ✅ | ✅ |
| SQLite 輸出 | ✅ | ✅ | ✅ | ✅ | ✅ |
| WebUI 儀表板 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 記憶體快取 | ✅ | ✅ | ✅ | ✅ | ✅ |
| Proxy 輪換 | ✅ | ✅ | ✅ | ✅ | ✅ |

> ⚠️ = 需要登入先有完整數據

## 快速開始

### 安裝

```bash
git clone https://github.com/Smart75850/smart-agent.git
cd smart-agent
pip install -r requirements.txt
playwright install chromium
```

### 基本用法

```bash
# B站搜索（唔使登入，即開即用）
python main.py --platform bilibili --keyword Python

# B站排行榜
python main.py --platform bilibili --type rank

# 全部平台搜索
python main.py --platform all --keyword Python
```

### CDP 模式（需登入平台）

```bash
# 1. 開 Chrome（已登入平台）
chrome --remote-debugging-port=9222

# 2. 用 CDP 模式行
set BROWSER_ENGINE=cdp
python main.py --platform zhihu --type hot --engine cdp
python main.py --platform xiaohongshu --keyword Python --engine cdp
```

### 輸出格式

```bash
# JSON（預設）
python main.py --platform bilibili --keyword Python

# CSV
set STORE_BACKEND=csv
python main.py --platform bilibii --keyword Python

# SQLite
set STORE_BACKEND=sqlite
python main.py --platform bilibili --keyword Python
```

### WebUI 模式

```bash
python -m api.main
# → http://localhost:8000
```

內建暗色主題儀表板，支援 WebSocket 即時日誌串流、JSON/CSV 下載

## v1.0 開源版

本倉庫為 Smart Agent 開源版 v1.0，包含完整的 5 平台內容採集功能。

> **Smart Agent Pro**（閉源）提供額外功能：微博/貼吧適配器、LangGraph AI 分析引擎（ContentRemix / CopyWriter / PicTactic / SentimentReader / TrendScout / ProductMiner）、SignSrv 簽名服務、Go 高性能版本、CookieBridge 擴展、MediaDownloader、Session 管理、Proxy 池、一鍵部署腳本等。如有需要請聯繫作者。

## 目錄結構

```
smart-agent/
├── main.py                  # CLI 入口
├── api/                     # WebUI + REST API
│   ├── main.py              # FastAPI 入口
│   ├── routers/             # API 路由
│   └── webui/               # 前端儀表板
├── src/
│   ├── agents/              # 平台適配器
│   ├── utils/               # 工具函數
│   └── mcp_tools/           # MCP Server
├── config/                  # 配置
├── constant/                # 常量
├── model/                   # 數據模型
├── store/                   # 存儲後端
├── proxy/                   # Proxy 管理器
├── base/                    # 基礎類
├── cache/                   # 快取
└── examples/                # 使用範例
