# Smart Agent — 實時狀態

> **呢個係三個工具（VS Code Claude / Terminal Claude Code / Codex）共享嘅單一事實來源。**
> **開工第一句就話「睇 STATUS.md」，唔好靠記憶。**

---

## 當前焦點

✅ Phase 1 引擎 + Phase 2 LangGraph + P1-P10 全部完成
⬜ 進行中：無（核心功能全部完成）
**下一步：API 層 pipeline 端點 + 集成測試 + 全平台實戰驗證**

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

## Pro 版第二階段（智能代理層）— ✅ 全部完成

### LangGraph 編排層
- `src/orchestrator/` — StateGraph DAG（graph.py / nodes.py / state.py / edges.py / pipeline.py）
- 雙模式管道：`simple`（搜索→合併→輸出）/ `full`（搜索→合併→7 Agent→報告）
- Fan-out 並行搜索 5 平台 → merge_results 去重排序 → Agent 線性鏈 → format_output
- SqliteSaver checkpointer、重試機制、adapter 緩存
- CLI `--type aggregate --engine langgraph --pipeline full`

### 7 個 AI Agent（P1-P7）

| # | Agent | 文件 | 說明 |
|:--|-------|------|------|
| P1 | Trend Scout | `agents/trend_scout.py` | 爆款識別分析（viral_score / trend_reason） |
| P2 | Product Miner | `agents/product_miner.py` | 選品深入分析（monetization_potential / 競爭優勢） |
| P3 | Video Analyst | `agents/video_analyst.py` | 視頻結構拆解（hook_type / pacing / structure_template） |
| P4 | Sentiment Reader | `agents/sentiment_reader.py` | 評論情緒分析（positive/neutral/negative%） |
| P5 | Copy Writer | `agents/copy_writer.py` | 營銷文案生成（headline/short/medium/long） |
| P6 | Content Remixer | `agents/content_remixer.py` | 數據分析/總結/改寫（summarize/analyze/rewrite） |
| P7 | Pic Tactic | `agents/pic_tactic.py` | 智能配圖策略（cover/social/trend，含英文 AI 提示詞） |

每個 Agent 支持：
- DeepSeek V4 Flash LLM 分析（無 API key 時自動降級為模板模式）
- 獨立 `run()` 直接調用 + `as_node()` LangGraph 節點集成
- Dataclass 類型化輸出 + `asdict()` 序列化

### 附加模塊（P8-P10）

| # | 模塊 | 文件 | 說明 |
|:--|------|------|------|
| P8 | Media Downloader | `downloader/media_downloader.py` | 批量下載封面+視頻（httpx 流式 + 瀏覽器輔助提取） |
| P9 | BaseAgent 重構 | `agents/base.py` | 抽取共享 LLM 調用邏輯，7 Agent 統一繼承 |
| P10 | Agent 接入 DAG | `graph.py` | 7 Agent 串入 LangGraph 線性鏈，`--pipeline full` 一鍵全流程 |

### 基礎設施

| 模塊 | 說明 |
|------|------|
| Camoufox 第三引擎 | Firefox 底層反檢測（C++ 指紋偽裝，WebGL/Canvas 隨機化） |
| CookieBridge | Chrome Extension (MV3) + Python HTTP 服務，一鍵同步瀏覽器登錄態 |
| DeepSeek API | `.env` 自動加載（python-dotenv），DeepSeek V4 Flash 驅動全部分析 |
| 降級模式 | 所有 Agent 無 API key 時自動降級為模板/熱度排序 |

---

## 待辦（按優先級）

### 🔴 P0 — 必須完成
- [ ] **API 層 pipeline 端點** — `POST /api/pipeline` 暴露 `run_pipeline()` 俾 WebUI 調用
- [ ] **全平台 full pipeline 實戰驗證** — 5 平台各跑一次 `--pipeline full`，確認無報錯

### 🟡 P1 — 應該完成
- [ ] **Agent 集成測試** — pytest 測試覆蓋 full pipeline 降級模式
- [ ] **Agent 並行化** — 將線性鏈改為 fan-out（product_miner / video_analyst / sentiment_reader 可並行）
- [ ] **個別 Agent 失敗不影響整體** — try/catch 包裝 agent node，單個失敗跳過繼續

### 🟢 P2 — 可以延後
- [ ] Docker 一鍵部署
- [ ] 微博、貼吧平台支援
- [ ] Golang 高性能版本

---

## 差異化定位

**Smart Agent Pro 嘅核心競爭力：**
1. **Camoufox MCP 反檢測數據層** — 唔係 Playwright CDP 咁簡單
2. **電商爆款分析場景** — 唔係通用爬蟲，係針對帶貨/選品嘅深度分析
3. **LangGraph 智能代理編排** — 自動化商業決策流程（7 Agent 全鏈路）
4. **DeepSeek V4 Flash** — 低成本 LLM 驅動，無 API key 自動降級

---

## 市場分析與商業策略（2026-05-26 更新）

### 競爭對手定價

| 工具 | 定位 | 定價 | 核心功能 |
|------|------|:--:|------|
| 蟬媽媽 | 抖音/快手數據分析 | ¥299-¥2999/月 | 爆款追蹤、達人分析、選品 |
| 飛瓜數據 | 短視頻分析 | ¥299-¥1999/月 | 帶貨數據、商品分析 |
| 新榜 | 全平台內容數據 | ¥199-¥999/月 | 內容監測、賬號分析 |
| 抖查查 | 抖音數據 | ¥99-¥599/月 | 搜索排名、熱詞 |
| 卡思數據 | 短視頻分析 | ¥168-¥888/月 | 競爭分析、輿情監控 |

### MediaCrawler (阿江) 模式分析

| 維度 | 阿江 | Smart Agent Pro |
|------|------|------|
| 變現 | 賣課程 ¥258 | 工具 + 課程（規劃中） |
| 客戶 | 想學技術嘅開發者 | 帶貨主播 / 電商運營 / 開發者 |
| 核心壁壘 | JS 簽名引擎（脫瀏覽器） | Camoufox 反檢測 + LangGraph Agent |
| 護城河 | 技術難度高，需專人逆向 | 反檢測強，AI 編排獨特 |
| 可複製性 | 低（需持續逆向維護） | 中等（Camoufox 開源） |
| 持續收入 | 每期新學員 | 月費訂閱 + 課程 |

### 脫瀏覽器技術評估

| 平台 | 難度 | 達成率 | 說明 |
|------|:--:|:--:|------|
| B站 | 🟢 0 | 100% | API 完全開放，已實現 |
| 知乎 | 🟢 0 | 100% | search API 無反爬 |
| 快手 | 🟡 中等 | 60% | 有公開實現參考 |
| 小紅書 | 🔴 極難 | 15% | WASM 逆向，需專人 |
| 抖音 | 🔴 極難 | 5% | 字節跳動安全團隊維護，每月更新 |

- 第三方簽名 API：SignSrv 等，每次 ¥0.01-¥0.05，包月 ¥500-¥2000（多數已斷更）
- 阿江做到脫瀏覽器係因為有專人全職逆向（成本 ¥20K-¥40K/月）

### 兩條路線對比

| | 賣工具 (SaaS) | 賣課程 + 工具 |
|------|:--:|:--:|
| 前期投入 | 高（WebUI/Docker/客服） | 中等（錄課程 + 開源工具） |
| 持續成本 | 高（服務器/維護） | 低（課程一次錄製） |
| 客戶獲取 | 難（同蟻媽媽競爭） | 易（SEO + GitHub + B站） |
| 變現周期 | 長（月費，需基數） | 短（賣一單賺一單） |
| 護城河 | 弱 | 強（實戰經驗） |
| 適合現階段 | 🟡 | 🟢 **推薦** |

### 策略建議

1. **短期**：完善 API 層 + 全平台驗證 + 準備「Camoufox + LangGraph 反檢測 AI Agent 實戰」課程
2. **中期**：課程上線（¥199-¥299），目標 100 學員首月；工具以「課程配套」形式提供
3. **長期**：課程月入 >¥10 萬後，請專人逆向簽名，再考慮獨立 SaaS

### 市場定位

- **唔同蟻媽媽爭** — 佢哋做數據 dashboard，我哋做 AI 分析 + 文案生成
- **唔同阿江爭** — 佢教 HTTP 逆向，我哋教反檢測 + AI Agent
- **核心差異**：Camoufox C++ 指紋偽裝 + LangGraph 智能編排 + 7 個垂直 Agent

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

**2026-05-26 Full Pipeline（keyword=AI绘画，platform=bilibili，DeepSeek LLM）**：
- B站搜索 3 ✅ → TrendScout ✅ → ProductMiner ✅ → VideoAnalyst ✅
- → SentimentReader ✅ → CopyWriter ✅ → ContentRemixer ✅ → PicTactic ✅
- 7/7 Agent 全鏈路 DeepSeek V4 實時分析通過

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

*最後更新：2026-05-26 — P10 Agent 接入 LangGraph DAG + DeepSeek API 配置完成*
