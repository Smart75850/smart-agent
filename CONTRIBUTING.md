# 貢獻指南

多謝你有興趣貢獻 Smart Agent！無論係報 bug、提功能、定係直接寫 code，都歡迎。

## 目錄

- [回報問題](#回報問題)
- [提交功能請求](#提交功能請求)
- [開發流程](#開發流程)
- [程式碼規範](#程式碼規範)
- [提交 PR](#提交-pr)

## 回報問題

開 Issue 用 Bug Report 模板，請俾齊：

- 目標平台同操作類型
- 瀏覽器引擎（playwright / cdp）
- 完整嘅 error log（copy & paste，唔好截圖）
- Python 版本、有冇開 proxy

## 提交功能請求

開 Issue 用 Feature Request 模板，清楚描述：

- 想解決嘅問題
- 建議嘅解決方案
- 替代方案（如果有）

## 開發流程

```bash
# 1. Fork 之後 clone
git clone https://github.com/你的帳號/smart-agent.git
cd smart-agent

# 2. 開 feature branch
git checkout -b feat/your-feature-name

# 3. 裝依賴
pip install -r requirements.txt
playwright install chromium

# 4. 開工！
```

### 如果想加新平台

1. 喺 `constant/platform.py` 加 `PlatformType` 枚舉
2. 繼承 `base/platform_base.py` 嘅 `PlatformAdapter`，實作 5 個方法：
   - `search(keyword)` — 關鍵字搜索
   - `hot()` — 熱榜/排行榜
   - `detail(item_id)` — 內容詳情
   - `comment(item_id)` — 留言爬取
   - `user(user_id)` — 用戶主頁
3. 喺 `main.py` 嘅 `_ADAPTERS` 度註冊
4. PR 時附上測試結果

### 如果想加儲存後端

1. 喺 `store/` 下開新檔案，實作 `save(data, output_dir, platform) -> str`
2. 喺 `store/__init__.py` 嘅 `_LAZY_MAP` 同 `get_store()` 度註冊

## 程式碼規範

- **命名即文檔** — 唔好寫冗餘註解
- 變數／函數用 snake_case
- class 用 PascalCase
- async / await 唔用 callback
- import 順序：stdlib → 第三方 → 內部

## Pre-commit（可選）

如果想 commit 前自動檢查格式：

```bash
pip install pre-commit
pre-commit install
```

## 提交 PR

1. 確保 branch 係基於最新嘅 main
2. PR title 精簡（`feat: 加 XXX 平台支援` / `fix: 修復 YYY bug`）
3. PR description 寫清楚改咗咩、點樣測試
4. 如果加咗新功能，更新對應嘅 README 或 doc

## 有問題？

直接開 Discussion，或者喺 Issue 度問。
