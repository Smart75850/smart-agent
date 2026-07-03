# smart-agent — AI Agent 配置

## 项目概述

**多平台 AI 内容分析引擎**——输入关键词，自动搜索知乎/B站/小红书/抖音等 7 个平台，7 个 AI Agent 并联分析爆款趋势、竞品策略、用户情绪，输出结构化报告。

**关键 metric（按诚实标注铁律）**：

| Metric | Value | Verified | Source | Date |
|---|---|---|---|---|
| 全量测试通过率 | 71/71 = 100% | ✅ | `pytest` 2026-06-12 | 2026-06-12 |
| Smoke test | 5/5 PASS (0.02 秒) | ✅ | `pytest tests/test_smoke.py` 2026-07-03 | 2026-07-03 |
| 平台数 | 7 | ✅ | `constant/platform.py` PlatformType | 2026-06-12 |
| Crawl 类型 | 6 | ✅ | `constant/platform.py` CrawlType | 2026-06-12 |
| HTTP 直连 (✅) | 3 平台（B站 / 微博 / 贴吧）| ✅ | `STATUS.md` 实测 | 2026-06-12 |
| HTTP 直连 (⚠️ 需 CDP) | 4 平台（知乎 / 快手 / 抖音 / 小红书）| ✅ | `STATUS.md` 实测 | 2026-06-12 |
| 真实场景实测 | 3 项全过 | ✅ | `STATUS.md` 表格 | 2026-06-12 |
| 最新版本 | v1.1.0 | ✅ | `CHANGELOG.md` | 2026-06-10 |

## 「最小可信改动」3 原则应用

呢个项目**已经高度成熟**（71/71 测试 + 完整文档 + 已有 smoke test）。改造策略：**唔重写已有嘢，只补 verified 标注 + 自动化审计**。

### 原则 1：成本极低就做（Low-Hanging Fruit First）

- ✅ 唔写新 smoke test（已有 `tests/test_smoke.py` 5 项 0.02 秒）
- ✅ 加 `scripts/audit.sh` 而唔系搭 CI
- ✅ 加 verified 标注到现有 `STATUS.md`（事实来源）

### 原则 2：未知就标注（Explicit Uncertainty）

- ✅ STATUS.md 加 Verified Metrics 表（7 项 metric）
- ✅ 「⚠️ 需 CDP」明确标「HTTP 不够，需 Playwright/CDP」
- ✅ 撞到新数据时先标 `verified: false`，再 verify 后改 `true`

### 原则 3：测试唔好过设计（Test as Documentation）

- ✅ 现有 `tests/test_smoke.py` 5 项 0.02 秒（唔 over-spec）
- ✅ 测试粒度 ≈ 改动粒度
- ✅ audit.sh 检查结构而非编译（即时反馈）

## 工作流

### 改代码后
```bash
# 1. 跑 smoke test（验证基础结构未坏）
source .venv/bin/activate
python -m pytest tests/test_smoke.py -v

# 2. 跑全量测试（如果改动跨模块）
python -m pytest tests/ -v

# 3. 跑 audit（验证文档 + Git 状态）
bash scripts/audit.sh

# 4. commit + push
git add -A
git commit -m "..."
git push origin master
```

### 更新 STATUS.md / PROGRESS.md / CHANGELOG.md
```bash
# 1. 更新对应字段
# 2. 加 verified: true/false + source + date
# 3. 跑 audit.sh 验证
bash scripts/audit.sh
```

### 红线（STATUS.md 🔴 必读）

- ❌ 任何公开位置**绝不出現價格**（¥399、¥365 等數字）
- ❌ 絕不出現「商务合作」「商业」「购买」「售价」「定价」等商業字眼
- ✅ 公開定位：**學習與學術研究**
- 詳見 `memory/platform_publishing_rules.md`

## 主动求助铁律（ID 128）

如果 AI 唔识 / 唔确定 / 可能错，即刻搵大佬，唔好等大佬发现问题。

格式按 [claude-config/CLAUDE.md § AI 主动求助铁律](https://github.com/Smart75850/claude-config)。

## 关联资产

- [smart-agent-进化计划-v2](https://github.com/Smart75850/claude-config/blob/main/knowledge-star/)：MCP 协议替代 REST 路线
- [project_init.sh](https://github.com/Smart75850/claude-config/blob/main/knowledge-star/project_init.sh)：新项目骨架生成器
- [mcp-x-mac-seed 改造](https://github.com/reverendish/mcp-x-mac-seed)：姊妹项目嘅 verified + smoke test 范例
- [Hermes Glass](https://github.com/Smart75850/hermes-glass)：WebUI for Hermes Agent