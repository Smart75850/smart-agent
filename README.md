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
python main.py --platform bilibili --keyword Python

# SQLite
set STORE_BACKEND=sqlite
python main.py --platform bilibili --keyword Python
```

### WebUI 模式

```bash
python -m api.main
# → http://localhost:8000
```

內建暗色主題儀表板，支援 WebSocket 即時日誌串流、JSON/CSV 下載、任務輪詢。

## 項目結構

```
smart-agent/
├── main.py                     # CLI 入口
├── api/                        # WebUI（FastAPI + Vanilla SPA）
│   ├── main.py                 # FastAPI 應用
│   ├── routers/                # API 端點
│   │   ├── platforms.py        # 平台列表與設定
│   │   ├── crawl.py            # 非同步爬蟲任務排程
│   │   ├── data.py             # 結果查詢
│   │   └── ws.py               # WebSocket 日誌廣播
│   └── webui/
│       └── index.html          # 暗色主題 SPA
├── config/
│   └── settings.py             # 集中設定
├── base/
│   └── platform_base.py        # PlatformAdapter 抽象類
├── model/
│   └── platform_models.py      # 數據模型（VideoItem, NoteItem）
├── constant/                   # 列舉與常數
│   ├── __init__.py
│   └── platform.py             # PlatformType, CrawlType, ErrorCode
├── src/
│   ├── agents/                 # 各平台爬蟲 Adapter
│   │   ├── bilibili_adapter.py # B站（搜索、排行榜、評論）
│   │   ├── xiaohongshu_adapter.py  # 小紅書（搜索、詳情、評論）
│   │   ├── douyin_adapter.py   # 抖音（搜索、用戶、評論）
│   │   ├── zhihu_adapter.py    # 知乎（搜索、熱榜、評論）
│   │   └── kuaishou_adapter.py # 快手（搜索、熱榜）
│   ├── mcp_tools/              # MCP Server 工具
│   │   └── server.py           # fastmcp 服務端
│   └── utils/
│       ├── browser_service.py  # Playwright / CDP 瀏覽器控制
│       └── logger.py           # 統一日誌
├── store/                      # 儲存後端
│   ├── json_store.py           # JSON 輸出
│   ├── csv_store.py            # CSV 輸出（utf-8-sig）
│   └── sqlite_store.py         # SQLite（自動建表）
├── proxy/
│   └── proxy_manager.py        # 輪詢代理池
├── cache/
│   └── memory_cache.py         # 記憶體快取（TTL）
├── examples/
│   ├── basic_usage.py          # 基本用法範例
│   └── cdp_mode.py             # CDP 模式範例
└── .env.example                # 環境變數範本
```

## 免责声明

本项目仅供个人学习与学术研究使用。详见 [完整免责声明](DISCLAIMER.md)。

## License

NON-COMMERCIAL LEARNING LICENSE 1.0
