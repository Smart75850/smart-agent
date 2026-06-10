# Changelog

## v1.1.0 (2026-06-10) — Scrapling 2.0 + CDP 修复 🛡️

### 架构升级: Scrapling Adaptive Framework
- **src/adaptive/** — Scrapling 反反爬引擎集成：TLS 指纹伪装 + 自適應元素定位 + SQLite 指紋存儲
- **src/fetchers/** — 三層 Fetcher 架構：Light → Smart → Stealth，自動升級
- **src/cache/** — Response cache with WAL mode SQLite

### 抖音/小红书 CDP 修复
- 抖音搜尋改為 CDP Chrome（真實 TLS 繞過 verify_check）
- 小紅書搜尋改為 CDP Chrome（真實 TLS，防封殺）
- `douyin_http.py` + `xhs_http.py` — 純 HTTP 客戶端（零瀏覽器依賴）
- `anti_bot_escalator.py` — 反爬升級策略
- 新增 `docs/DOUYIN_FIX_GUIDE.md` — 新機部署指南

### MCP 工具
- `mcp_tools/smart_fetch_server.py` — curl_cffi TLS 指紋偽裝 + 瀏覽器 UA

### 已知限制
- 抖音 a_bogus 簽名 + 小紅書 x-s 簽名僅在 Pro 版提供
- `sign_srv/platforms/douyin.py` 為私有模組

## v1.0.0 (2026-05-30) — 正式版發布 🚀

### Agent v2 準確度提升
- **Phase A**: 7 Agent Prompt 重寫 — Role + Few-Shot + Quality Criteria + Edge Cases
- **Phase B**: Pydantic 結構化輸出 — JSON parse fail 5-10% → 0%
- **Phase C**: Evaluation Framework — 5 維度自動評分 + LLM-as-Judge + Regression Runner
- **Phase D**: Critic 自我修正 — review-retry loop，壞輸出攔截率 100%
- **4-Block Prompt**: Anthropic 2026 最佳實踐，SentimentReader +26 分
- **Dynamic Few-Shot**: trace_collector 接入，高分輸出自動成為示例
- **最終驗收**: 161 條數據，平均 84.6 分，6/6 平台全通

### WebUI MVP 重設計
- 左側固定導航欄 + Dashboard 首頁 + Agent 時間線 + Chip 選擇器 + Dark/Light 主題

### HTTP 直連突破
- 抖音搜索免 a_bogus（sessionid+ttwid 純 HTTP）
- B站評論純 HTTP（Wbi 簽名 + curl_cffi + BV→AV 轉換）
- 知乎/微博/貼吧 session 輕量健康檢查

### 基礎設施
- 瀏覽器重複啟動修復（`is_running` 檢查 + `asyncio.Lock`）
- `api/main.py` UsageMiddleware import 順序修復
- session_manager 三層 fallback（CDP → Persistent → 賬號輪換）

---

## v0.3.0 (2026-05-26) — 部署 & 高性能版

### 新增
- **Go 高性能版本 (P15)**：Go 殼 + Python 腦架構，6.7MB 單二進制，零外部依賴
  - Go HTTP API Server (net/http，替代 FastAPI)
  - Go DAG Orchestrator (goroutine fan-out，替代 LangGraph)
  - Python Sidecar (sidecar_server.py，封裝 5 Adapter + 7 Agent)
  - 實測 Full Pipeline 72s（5 平台搜索 + 7 Agent 全鏈路）
- **Windows 一鍵部署 (P13)**：deploy.ps1 + deploy.bat，6 步自動化安裝
- **Docker 一鍵部署 (P14)**：deploy-docker.ps1（5 步構建+啟動，支持 --WithMySQL）
- **Agent 並行化 (P11)**：兩階段 Send fan-out（Level1: product/video/sentiment，Level2: copy/remix/pic）
- **API pipeline 端點 (P0)**：POST /api/pipeline，非同步執行，GET 輪詢結果
- **全平台 full pipeline 實戰驗證**：7/7 平台唔崩，B站/小紅書/知乎/微博有真實數據
- **WebUI 雙模式界面**：單平台爬取 + Pipeline 全流程分析（多平台勾選 + Agent 報告卡片）
- **Go API 前端服務**：Go server 支援 WebUI 靜態文件 + /api/platforms 端點
- **微博 + 貼吧適配器 (P16)**：weibo_adapter.py + tieba_adapter.py（search/hot/detail/comment/user）

### 修改
- `src/orchestrator/graph.py` — 線性鏈改兩階段 fan-out + 條件路由 + Send API
- `src/orchestrator/nodes.py` — ADAPTER_MAP 加 weibo/tieba
- `api/routers/crawl.py` — _ADAPTERS 加 WeiboAdapter/TiebaAdapter
- `api/routers/pipeline.py` — _DEFAULT_PLATFORMS 加 weibo/tieba
- `api/webui/index.html` — 重寫為雙模式界面（單平台爬取 + Pipeline 全流程分析）
- `go/internal/api/server.go` — 加 WebUI 靜態文件服務 + /api/platforms + /api/ws stub
- `src/aggregator.py` — 加 weibo/tieba 平台 ID 提取
- `src/aggregator.py` — 加 weibo/tieba 平台 ID 提取
- `constant/platform.py` — PlatformType 加 WEIBO/TIEBA
- `api/routers/platforms.py` — _PLATFORMS 加微博/貼吧
- `docker-compose.yml` — 移除過時 version 字段
- `STATUS.md` — 新增 P11-P15 驗證記錄 + Go 版架構文檔

### 部署腳本
- `deploy.ps1` / `deploy.bat` (P13) — Windows 本地一鍵部署
- `deploy-docker.ps1` (P14) — Docker 一鍵部署
- `deploy-go.ps1` (P15) — Go 版本構建+部署

---

## v0.2.0 (2026-05-26) — Agent 智能分析層

### 新增
- **7 個 AI Agent** (P1-P7)：TrendScout / ProductMiner / VideoAnalyst / SentimentReader / CopyWriter / ContentRemixer / PicTactic
- **Media Downloader** (P8)：httpx 流式下載 + 瀏覽器輔助媒體 URL 提取（5 平台封面+視頻）
- **BaseAgent 基類重構** (P9)：抽取共享 LLM 調用邏輯，7 Agent 統一繼承
- **Agent 接入 LangGraph DAG** (P10)：`--pipeline full` 一鍵跑 7 Agent 全鏈路分析
- **DeepSeek V4 Flash 集成**：`.env` 自動加載（python-dotenv），驅動全部分析
- **LangGraph 雙模式管道**：`simple`（搜索合併）/ `full`（搜索→合併→7 Agent 分析→報告）
- **Camoufox 第三引擎**：Firefox C++ 反檢測（WebGL/Canvas/AudioContext 指紋偽裝）
- **CookieBridge**：Chrome Extension MV3 + Python HTTP 服務，一鍵同步瀏覽器登錄態
- **Agent 降級模式**：所有 Agent 無 API key 時自動降級為模板/熱度排序

### 修改
- `src/orchestrator/state.py` — 加 8 字段（pipeline_mode + 7 Agent 輸出）
- `src/orchestrator/graph.py` — 加 7 Agent 節點 + 條件路由
- `src/orchestrator/nodes.py` — format_output 支持 full 模式附加 Agent 報告
- `src/orchestrator/pipeline.py` — run_pipeline 支持 pipeline_mode 參數
- `config/settings.py` — 加 .env 自動加載 + DeepSeek 配置
- `main.py` — CLI 加 `--pipeline full` 選項
- `src/agents/douyin_adapter.py` — 加 cover_url 字段
- `src/agents/kuaishou_adapter.py` — 加 cover_url 字段 + _pick_best_cover()
- `src/utils/browser_service.py` — Camoufox 分支 + CookieBridge 注入
- `requirements.txt` — 加 httpx/camoufox，清除非必要依賴

### 修復
- browser_service.py 缺 logger import（P0）
- requirements.txt 含未使用依賴（P0）
- PicTactic _PLATFORM_DEFAULTS 缺 target_platform 字段（P1）
- CopyWriter as_node() 漏傳 video_breakdowns（P1）
- model/platform_models.py 字段與 adapter 輸出不匹配（P1）
- TrendScout as_node() 繞過 run() 直接調用內部方法（P2）
- graph.py 未使用 settings import（清理）
- api/routers/crawl.py 未使用 Optional import（清理）

---

## v0.1.0 (2026-05-24) — 核心引擎

### Initial Release
- **5 platforms**: Bilibili, Xiaohongshu (RED), Douyin, Zhihu, Kuaishou
- **5 operations per platform**: search, hot/rank, detail, comment, user
- **Nested comments**: recursive reply extraction for all platforms
- **6 storage backends**: JSON, CSV, JSONL, Excel, SQLite, MySQL
- **WebUI**: FastAPI + Vanilla JS SPA with WebSocket real-time logs
- **MCP Server**: fastmcp integration for AI agent tool calling
- **Dual engine**: Playwright (headless) and CDP (authenticated session)
- **Proxy pool**: round-robin rotation with env-var configuration
- **Cache**: in-memory TTL cache for deduplication
- **CI/CD**: GitHub Actions with smoke tests and linting
