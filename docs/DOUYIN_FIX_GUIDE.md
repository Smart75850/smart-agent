# 抖音搜索修復 — 新機上手指令

## 背景

抖音最新反爬已強制要求 `a_bogus` 簽名 + `msToken` + `verifyFp`。純 HTTP（httpx）因為 TLS 指紋唔同真實瀏覽器，會被抖音檢測到並觸發 `verify_check`（空結果）。

**解決方案**：改為經 CDP Chrome 發請求。用真實 Chrome 嘅 TLS 指紋，抖音分唔出。

---

## 另一部電腦操作（照住做）

### 第一步：更新代碼

```bash
cd smart-agent-pro
git pull origin main
```

### 第二步：確認依賴

```bash
pip install -r requirements.txt
playwright install chromium
```

### 第三步：啟動 CDP Chrome

```bash
# Windows
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222

# Mac
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222

# Linux
google-chrome --remote-debugging-port=9222
```

### 第四步：登入抖音

喺啱啱打開嗰個 Chrome 窗口：
1. 去 https://www.douyin.com
2. 人手登入（手機掃碼）
3. 確認見到首頁推薦內容（唔係登錄頁）
4. **Chrome 唔好關**，縮小就得

### 第五步：測試

```bash
python main.py --platform douyin --keyword Python --limit 10
```

見到結果即係成功。

---

## 而家全部平台嘅正確用法

| 平台 | 命令 | 前置條件 |
|:---|:---|:---|
| B站 | `python main.py --platform bilibili --keyword xx` | 冇 |
| 小紅書 | `python main.py --platform xiaohongshu --keyword xx` | CDP Chrome 已登入小紅書 |
| 抖音 | `python main.py --platform douyin --keyword xx` | CDP Chrome 已登入抖音 |
| 知乎 | `python main.py --platform zhihu --keyword xx` | CDP Chrome 已登入知乎 |
| 快手 | `python main.py --platform kuaishou --keyword xx` | CDP Chrome 已登入快手 |
| 微博 | `python main.py --platform weibo --keyword xx` | CDP Chrome 已登入微博 |
| 貼吧 | `python main.py --platform tieba --keyword xx` | 冇（curl_cffi TLS） |
| 通用 | `python main.py --platform generic --keyword "URL"` | 冇 |
| 全部 | `python main.py --platform all --keyword xx` | CDP Chrome 登入晒 |

---

## 原理

```
之前：httpx → Python TLS 指紋 → 抖音 verify_check → ❌
而家：CDP Chrome → 真實 Chrome TLS → 抖音以為係真人 → ✅
```

`a_bogus` 簽名、`msToken`、`verifyFp` 全部由 CDP Chrome 嘅 JavaScript 自動生成，
唔需要我哋手動逆向。因為用嘅係真實瀏覽器，抖音冇辦法分辨。

---

## 常見問題

**Q: Chrome 可以 headless 嗎？**
A: 唔可以。headless 嘅 GPU 指紋唔同，會被抖音檢測。

**Q: 每次都要開 Chrome？**
A: 係。Chrome 要保持開住。你可以縮小佢，但唔可以關。

**Q: 如果顯示「搜索被拒」？**
A: 去 CDP Chrome 重新登入抖音，然後再試。

**Q: sessionid 過期？**
A: 關閉 Chrome → 重新開 CDP Chrome → 重新登入抖音。
   通常 24-48 小時先會過期一次。
