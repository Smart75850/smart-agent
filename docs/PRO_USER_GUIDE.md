# Smart Agent Pro — 使用指南

## 目录

1. [安装部署](#安装部署)
2. [每日起步（2 分鐘）](#每日起步)
3. [WebUI 使用](#webui-使用)
4. [CLI 命令行](#cli-命令行)
5. [AI 全流程分析](#ai-全流程分析)
6. [评论采集](#评论采集)
7. [配置说明](#配置说明)
8. [常见问题](#常见问题)

---

## 安装部署

### 方式一：Docker（推荐）

```bash
docker compose up -d
# 打开 http://localhost:8000
```

### 方式二：Windows 一键部署

双击 `deploy.bat`，自动安装依赖并启动 WebUI。

### 方式三：手动安装

```bash
pip install -r requirements.txt
playwright install chromium
python -m api.main
# 打开 http://localhost:8000
```

---

## 每日起步（2 分鐘）

Pro 版嘅纯 HTTP 直连需要从浏览器收割一次会话。**每日做一次**，之后全日唔使再开浏览器。

### Step 1：启动 CDP Chrome

```bash
# Windows：双击 scripts\start_cdp_chrome.ps1
# 或手动：
chrome --remote-debugging-port=9222
```

### Step 2：登录平台

喺呢个 Chrome 视窗手动登录：
- 抖音：扫码登录
- 小红书：扫码登录
- 其他平台：如需要也可以登录（非必须）

### Step 3：收割会话

```bash
python -c "import asyncio; from src.utils.session_manager import harvest_all; asyncio.run(harvest_all())"
```

输出显示全部 OK 即完成。可以关 Chrome，之后全日纯 HTTP 直连。

> **提示**：WebUI 启动时会自动开启会话守护（15 分钟巡检），如果 Chrome 一直开着，会话过期会自动重新收割。

---

## WebUI 使用

启动后打开 `http://localhost:8000`。

### 单平台采集

1. 左侧导航 → 「多平台采集」
2. 选择平台（可多选）
3. 输入关键词
4. 点击「开始采集」
5. 下载结果（JSON/CSV）

### 全流程 AI 分析

1. 左侧导航 → 「全流程分析」
2. 输入关键词
3. 选择平台
4. 选择分析 Agent（默认全选）
5. 点击「开始分析」
6. 等待 Agent 链完成，查看报告

---

## CLI 命令行

### 单平台搜索

```bash
# 纯 HTTP 直连（Pro 版全部 7 平台支持）
python main.py --platform douyin --keyword AI工具         # 抖音
python main.py --platform xiaohongshu --keyword 穿搭       # 小红书
python main.py --platform bilibili --keyword Python        # B站
python main.py --platform all --keyword 美食               # 全平台
```

### 全流程 AI 分析

```bash
# 一键搜索 + 7 Agent 全链路分析
python main.py --keyword AI工具 --pipeline full --platform bilibili,douyin,zhihu

# 只做舆情分析（搜索 + 评论采集）
python main.py --keyword 美食 --pipeline sentiment --platform bilibili
```

### 断点续爬

```bash
# 中断后自动续传
python main.py --platform bilibili --keyword AI --limit 200 --resume
```

---

## AI 全流程分析

`--pipeline full` 会依次执行 7 个 AI Agent：

```
搜索（5 平台并发）
  → 评论收割（每平台 Top5）
  → Trend Scout（爆款识别）
  → Product Miner（选品分析）∥ Video Analyst（视频拆解）∥ Sentiment Reader（评论情绪）
  → Copy Writer（营销文案）∥ Content Remixer（内容改写）∥ Pic Tactic（配图策略）
  → 输出完整报告
```

### 7 个 Agent 说明

| Agent | 做什么 | 输出 |
|------|------|------|
| Trend Scout | 识别爆款潜力内容 | 爆款评分 + 趋势分析 |
| Product Miner | 挖掘可带货商品 | 商品列表 + 变现潜力 |
| Video Analyst | 拆解视频结构 | 钩子类型 + 结构模板 |
| Sentiment Reader | 分析评论情绪 | 情绪分布 + 购买信号 |
| Copy Writer | 生成营销文案 | 多平台多版本文案 |
| Content Remixer | 赛道分析/内容改写 | 竞争格局 + 切入建议 |
| Pic Tactic | 封面配图策略 | AI 绘画提示词 + 构图 |

### 无 API Key 降级模式

未配置 DeepSeek API Key 时，Agent 会自动降级为模板模式（纯热度排序+模板输出），仍可正常使用。

---

## 评论采集

Pro 版支持纯 HTTP 评论采集（无需浏览器）：

| 平台 | 评论采集 | 方式 |
|------|:--:|------|
| B站 | ✅ | HTTP 直连（Wbi 签名） |
| 知乎 | ✅ | HTTP 直连 |
| 快手 | ✅ | HTTP 直连 |
| 抖音 | ⚠️ | 需 CDP 浏览器 |
| 小红书 | ⚠️ | 需登录 |
| 微博 | ⚠️ | API 不稳定 |
| 贴吧 | ⚠️ | API 不稳定 |

---

## 配置说明

编辑 `.env` 文件：

```bash
# DeepSeek API（可选，不配置则用降级模式）
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_MODEL=deepseek-chat       # 或 deepseek-reasoner

# 浏览器引擎（auto = 优先 CDP，无则 Playwright）
BROWSER_ENGINE=auto

# 代理（可选）
HTTP_PROXY=http://127.0.0.1:7890

# 存储后端（默认 JSON）
STORE_BACKEND=json
```

---

## 常见问题

**Q: 纯 HTTP 和浏览器模式有什么区别？**
A: 纯 HTTP 直连速度快 10 倍（~500ms vs ~3s），不需开浏览器，适合服务器部署。

**Q: 为什么要每日收割会话？**
A: 抖音和小红书的登录 Cookie 有时效（几小时到 1-2 天），收割一次后保存到本地，之后纯 HTTP 直连复用。

**Q: 收割后可以关 Chrome 吗？**
A: 可以。收割的会话保存到 `browser_data/` 目录，关了 Chrome 也能用。下次过期了再开 Chrome 收割一次。

**Q: 全流程分析很慢？**
A: 正常。7 个 Agent 依次调用 LLM，5 平台约 3-4 分钟。可减少平台数或 limit 提速度。

**Q: 没有 DeepSeek API Key 能用吗？**
A: 能。Agent 自动降级为模板模式，搜索和评论采集不受影响。

**Q: 怎么更新？**
A: 重新下载最新 ZIP 包覆盖即可。如有新功能会通知。

---

## 免责声明

本软件仅供学习与学术研究使用，严禁用于任何商业用途。使用者须遵守各平台的用户协议与相关法律法规。因使用本软件产生的任何法律责任由使用者自行承担。
