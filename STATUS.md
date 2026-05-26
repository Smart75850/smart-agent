# Smart Agent — 實時狀態

> **呢個係三個工具（VS Code Claude / Terminal Claude Code / Codex）共享嘅單一事實來源。**
> **開工第一句就話「睇 STATUS.md」，唔好靠記憶。**

---

## 當前焦點

已完成：Phase 1 引擎全部 + Phase 2 LangGraph 骨架
進行中：補齊 Phase 2 專用 Agent
下一步：Trend Scout → Product Miner（核心商業流程）

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

### ❌ 未開始 — 按優先級排列

```
第一優先（核心商業流程）
  P1 — Trend Scout          爆款識別分析
  P2 — Product Miner        選品深入分析

第二優先（分析能力）
  P3 — Video Analyst        視頻結構拆解（鉤子/節奏/轉化點）
  P4 — Sentiment Reader     評論情緒分析

第三優先（產出能力）
  P5 — Copy Writer          營銷文案生成

第四優先（附加模塊）
  P6 — ContentRemixAgent    數據分析/總結/改寫
  P7 — PicTacticAgent       智能配圖生成
  P8 — Video/Image Downloader 批量下載
  P9 — CookieBridge         Chrome Extension
```

---

## Pro 版第三階段（長期）— 全部 ❌ 未開始

| 模塊 | 狀態 |
|------|:----:|
| Golang 高性能版本 | ❌ |
| 微博、貼吧平台支援 | ❌ |
| Docker 一鍵部署 | ❌ |

---

## 目錄結構（第日 split 做 4 個 repo）

目前一個 repo，但 module 邊界已劃清，第日 split 直接搬 folder 就得：

```
smart-agent/
├── src/
│   ├── core/            → Repo 1: smart-agent-core（引擎底層）
│   ├── platforms/       → Repo 2: smart-agent-platforms（平台適配器）
│   ├── agent/           → Repo 3: smart-agent-agent（AI 代理，最值錢）
│   ├── api/             → Repo 4: smart-agent-web（WebUI + MCP）
│   └── utils/
├── main.py
└── config/
```

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

*最後更新：2026-05-26 由 VS Code Claude 更新（最終版進度總表 + 目錄規劃）*
