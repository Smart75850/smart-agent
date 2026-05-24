<div align="center">

# Smart Agent

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)]()
[![License](https://img.shields.io/badge/License-NonCommercial-blue)]()
[![CI](https://github.com/Smart75850/smart-agent/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Smart75850/smart-agent/actions/workflows/ci.yml)
[![Platform](https://img.shields.io/badge/Platform-Bilibili%20|%20RED%20|%20Douyin%20|%20Zhihu%20|%20Kuaishou-orange)]()

Multi-platform content collection framework — pure crawler, structured data output.

</div>

⚠️⚠️⚠️⚠️ **This repository is for LEARNING PURPOSES ONLY. Commercial use is PROHIBITED.** [Full Disclaimer](DISCLAIMER.md)

## Features

| Feature | Bilibili | RED | Douyin | Zhihu | Kuaishou |
|---------|:-------:|:---:|:------:|:-----:|:--------:|
| Keyword Search | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| Trending / Hot | ✅ | — | — | ✅ | ⚠️ |
| Note Detail | — | ✅ | — | — | — |
| User Videos | — | — | ✅ | — | — |
| Comments | ✅ | ✅ | ✅ | ✅ | — |
| CDP Login | ❌ | ✅ | ✅ | ✅ | ✅ |
| JSON Export | ✅ | ✅ | ✅ | ✅ | ✅ |
| CSV Export | ✅ | ✅ | ✅ | ✅ | ✅ |
| SQLite Export | ✅ | ✅ | ✅ | ✅ | ✅ |
| Proxy Rotation | ✅ | ✅ | ✅ | ✅ | ✅ |
| WebUI Dashboard | ✅ | ✅ | ✅ | ✅ | ✅ |
| In-Memory Cache | ✅ | ✅ | ✅ | ✅ | ✅ |

> ⚠️ = Requires login for full data access

## Quick Start

### Installation

```bash
git clone https://github.com/Smart75850/smart-agent.git
cd smart-agent
pip install -r requirements.txt
playwright install chromium
```

### CLI Usage

```bash
# Bilibili search (no login required)
python main.py --platform bilibili --keyword Python

# Bilibili trending
python main.py --platform bilibili --type rank

# Fetch comments
python main.py --platform bilibili --type comment --keyword BV1rpWjevEip

# All platforms at once
python main.py --platform all --keyword Python
```

### Storage Backends

```bash
# JSON (default)
python main.py --platform bilibili --keyword Python

# CSV
set STORE_BACKEND=csv
python main.py --platform bilibili --keyword Python

# SQLite
set STORE_BACKEND=sqlite
python main.py --platform bilibili --keyword Python
```

### WebUI Mode

```bash
python -m api.main
# → http://localhost:8000
```

Interactive dashboard with real-time logs (WebSocket), JSON/CSV download, and task polling.

### CDP Mode (Login-Required Platforms)

```bash
# 1. Start Chrome with remote debugging (login to platforms first)
chrome --remote-debugging-port=9222

# 2. Run with CDP engine
set BROWSER_ENGINE=cdp
python main.py --platform zhihu --type hot --engine cdp
python main.py --platform xiaohongshu --keyword Python --engine cdp
python main.py --platform douyin --keyword Python --engine cdp
```

> Use CDP mode for platforms that require login cookies (RED, Douyin, Zhihu, Kuaishou).

## Project Structure

```
smart-agent/
├── main.py                     # CLI entry point
├── api/                        # WebUI (FastAPI + Vanilla SPA)
│   ├── main.py                 # FastAPI app with lifespan
│   ├── routers/                # API endpoints
│   │   ├── platforms.py        # Platform list & config
│   │   ├── crawl.py            # Async crawl task dispatch
│   │   ├── data.py             # Result retrieval
│   │   └── ws.py               # WebSocket log broadcast
│   └── webui/
│       └── index.html          # Dark-theme SPA
├── config/
│   └── settings.py             # Centralized settings from env
├── base/
│   └── platform_base.py        # PlatformAdapter ABC
├── model/
│   └── platform_models.py      # Data models (VideoItem, NoteItem)
├── constant/                   # Enums & constants
│   ├── __init__.py
│   └── platform.py             # PlatformType, CrawlType, ErrorCode
├── src/
│   ├── agents/                 # Platform adapters
│   │   ├── bilibili_adapter.py # Bilibili (search, rank, comments)
│   │   ├── xiaohongshu_adapter.py  # RED (search, detail, comments)
│   │   ├── douyin_adapter.py   # Douyin (search, user, comments)
│   │   ├── zhihu_adapter.py    # Zhihu (search, hot, comments)
│   │   └── kuaishou_adapter.py # Kuaishou (search, hot)
│   └── utils/
│       ├── browser_service.py  # Playwright / CDP browser control
│       └── logger.py           # Unified logging
├── store/                      # Storage backends
│   ├── json_store.py           # JSON file output
│   ├── csv_store.py            # CSV output (utf-8-sig for Excel)
│   └── sqlite_store.py         # SQLite (auto-create tables)
├── proxy/
│   └── proxy_manager.py        # Round-robin proxy pool
├── cache/
│   └── memory_cache.py         # In-memory cache with TTL
├── examples/
│   ├── basic_usage.py          # Basic CLI usage
│   └── cdp_mode.py             # CDP mode examples
└── .env.example                # Environment variable template
```

## Supported Platforms

### Bilibili (B站)
No login required for search, trending, or comments. Full access out of the box.

### Xiaohongshu / RED (小紅書)
Login required. Use CDP mode with pre-authenticated Chrome session. Supports search, note detail, and comments.

### Douyin / TikTok (抖音)
Login required. Use CDP mode. Search results, user videos, and comments are accessible after login.

### Zhihu (知乎)
Login required for hot list and comments; CDP mode recommended. Search without login loads the page but yields no results.

### Kuaishou (快手)
Login required for full data. Trending and search are partially available without login.

## Architecture

Smart Agent uses a layered architecture:

- **Adapter Layer** — `PlatformAdapter` ABC with unified `search()`, `hot()`, `detail()`, `comment()` interface. Each platform has its own adapter with platform-specific selectors.
- **Engine Layer** — Playwright (headless Chromium) for direct automation, or CDP mode to reuse an authenticated Chrome session.
- **Storage Layer** — Pluggable backends: JSON, CSV (with BOM for Excel), or SQLite (auto-creates tables per platform).
- **API Layer** — FastAPI + WebSocket for real-time log streaming and asynchronous crawl task management.
- **Infrastructure** — Round-robin proxy pool, TTL-based memory cache, typed enums for platforms and crawl operations.

## Tech Stack

- **Python 3.11+** with `asyncio` for async I/O
- **Playwright** — headless Chromium browser automation
- **CDP** — Chrome DevTools Protocol for authenticated sessions
- **FastAPI + WebSocket** — WebUI backend with real-time log streaming
- **SQLite / JSON / CSV** — multiple storage backends
- **Round-robin proxy pool** — environment-variable-driven proxy rotation

## Disclaimer

This project is for personal learning and academic research only. See [full disclaimer](DISCLAIMER.md).

## License

NON-COMMERCIAL LEARNING LICENSE 1.0
