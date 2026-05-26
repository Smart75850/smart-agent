# Smart Agent — 實時狀態

> **呢個係三個工具（VS Code Claude / Terminal Claude Code / Codex）共享嘅單一事實來源。**
> **開工第一句就話「睇 STATUS.md」，唔好靠記憶。**

---

## 當前焦點

✅ Phase 1 引擎全部 + Phase 2 LangGraph 骨架 + P1-P5 Agent + Camoufox + CookieBridge
⬜ 進行中：附加模塊（P7-P9）
下一步：ContentRemixAgent（数据分析/总结/改写）

---

## 倉庫狀態

| Repo | 可見性 | Branch | 用途 |
|------|:------:|--------|------|
| `Smart75850/smart-agent` | 🔓 公開 | `main` | 開源版（舊 code，未同步） |
| `Smart75850/smart-agent-pro` | 🔒 私人 | `main` | **Pro 版開發中（最新 code）** |
| `Smart75850/smart-agent-pro` | 🔒 私人 | `pro` | Pro 版備份 branch |

**開發目錄：** `C:\Users\guohu\smart-agent\`
**Remote：** `pro-origin` → `Smart75850/smart-agent-pro`

---

## Pro 版第一階段（核心引擎）— ✅ 全部完成

| # | 模塊 | 狀態 |
|:--|------|:----:|
| 1 | 抖音 a_bogus 本地簽名 | ✅ |
| 2 | 斷點續爬 + 去重（SQLite + --resume） | ✅ |
| 3 | 多賬號 IP 代理池 | ✅ |
| 4 | CDP 瀏覽器引擎（Playwright + Chrome CDP） | ✅ |
| 5 | B站搜索翻頁 | ✅ |
| 6 | 抖音評論翻頁 | ✅ |
| 7 | 抖音搜索翻頁 | ✅ |

---

## Pro 版第二階段（智能代理層）

### ✅ 已完成
- `src/orchestrator/` — LangGraph StateGraph（graph.py / nodes.py / state.py / edges.py / pipeline.py）
- 5 節點 pipeline：search_one（並行 5 平台）→ merge_results → llm_filter → llm_score → format_output
- 支援同步 `run_pipeline()` + 流式 `run_pipeline_stream()`
- SqliteSaver checkpointer、重試機制、adapter 緩存
- CLI `--type aggregate --engine langgraph`
- Review rounds 2 全部修復

### ✅ 已完成 — 5 個專用 Agent

| # | Agent | 文件 | Commit | 說明 |
|:--|-------|------|--------|------|
| P1 | Trend Scout | `agents/trend_scout.py` | `951117a` | 爆款識別分析（viral_score / trend_reason） |
| P2 | Product Miner | `agents/product_miner.py` | `82ae857` | 選品深入分析（monetization_potential / 競爭優勢） |
| P3 | Video Analyst | `agents/video_analyst.py` | `394b15c` | 視頻結構拆解（hook_type / pacing / structure_template） |
| P4 | Sentiment Reader | `agents/sentiment_reader.py` | `ba81aee` | 評論情緒分析（positive/neutral/negative%） |
| P5 | Copy Writer | `agents/copy_writer.py` | `f9f20cb` | 營銷文案生成（headline/short/medium/long） |

每個 Agent 均支持：
- DeepSeek V4 Flash LLM 分析（無 API key 時自動降級為模板模式）
- 獨立 `run()` 直接調用 + `as_node()` LangGraph 節點集成
- Dataclass 類型化輸出 + `asdict()` 序列化

### ✅ 已完成 — Camoufox 第三引擎

`BROWSER_ENGINE=camoufox` 支援 Firefox 底層反檢測（C++ 指紋偽裝，WebGL/Canvas/AudioContext 隨機化）。

| CLI | 行為 |
|-----|------|
| `--engine playwright` | Chromium + stealth（不變） |
| `--engine cdp` | 遠程 Chrome CDP（不變） |
| `--engine camoufox` | **新** Camoufox Firefox（C++ 反檢測） |
| `--engine langgraph` | 編排層（不變） |

改動：`settings.py`（8 配置項）、`browser_service.py`（camoufox 分支）、`xiaohongshu_adapter.py`（search/comment persistent context）、`main.py`（choices）

### ✅ 已完成 — CookieBridge

Chrome Extension (MV3) + Python stdlib HTTP 服务器，一键同步浏览器登录态。

| 组件 | 文件 |
|------|------|
| Extension | `src/cookie_bridge/extension/` (manifest.json / popup.html / popup.js) |
| Python 服务 | `src/cookie_bridge/server.py` (POST /cookies + GET /health) |
| 自动注入 | `browser_service.py` → `_load_platform_cookies()` |

用法：`python main.py --cookie-bridge` → Chrome Extension 点「同步」→ 5 平台 cookies 自动保存到 `browser_data/`

### ❌ 未開始

```
第五優先（附加模塊）
  P7 — ContentRemixAgent         數據分析/總結/改寫
  P8 — PicTacticAgent            智能配圖生成
  P9 — Video/Image Downloader    批量下載
```

---

## 差異化定位

**Smart Agent Pro 嘅核心競爭力：**
1. **Camoufox MCP 反檢測數據層** — 唔係 Playwright CDP 咁簡單
2. **電商爆款分析場景** — 唔係通用爬蟲，係針對帶貨/選品嘅深度分析
3. **LangGraph 智能代理編排** — 自動化商業決策流程

---

## Pro 版第三階段（長期）— 全部 ❌ 未開始

| 模塊 | 狀態 |
|------|:----:|
| Golang 高性能版本 | ❌ |
| 微博、貼吧平台支援 | ❌ |
| Docker 一鍵部署 | ❌ |

---

## 設計備註

⏸️ 拆多個 repo 嘅計劃 — 等 Phase 2 全部做完、代碼穩定咗先考慮。

---

## 驗證記錄

**2026-05-26 aggregate（keyword=美女，limit=5）**：
- B站 5 ✅ / 小紅書 5 ✅ / 抖音 5 ✅ / 知乎 5 ✅ / 快手 5 ✅
- 總計 25/25 全部通過

---

## 規則（所有 AI 工具遵守）

1. **每次開工先讀 STATUS.md**
2. **做完一件 task 就 update STATUS.md + commit**
3. **唔好一次改太多文件，逐個 module 搞**
4. **新 file 放啱目錄（core / platforms / agent / api）**

---

*最後更新：2026-05-26 — CookieBridge Chrome Extension 完成，服務驗證通過*
