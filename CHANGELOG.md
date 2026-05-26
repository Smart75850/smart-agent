# Changelog

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
