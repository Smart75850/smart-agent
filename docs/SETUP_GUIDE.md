# Smart Agent 开源版 — 上手指南

## 环境要求

- Python 3.11+
- Windows / macOS / Linux
- Chrome 浏览器（小红书、抖音需要）

## 安装

```bash
git clone https://github.com/Smart75850/smart-agent.git
cd smart-agent
pip install -r requirements.txt
playwright install chromium
```

## 三步上手

### 第一步：启动 CDP Chrome

**Windows（双击运行）：**
```powershell
.\scripts\start_cdp_chrome.ps1
```

**或手动启动：**
```bash
# Windows
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222

# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222

# Linux
google-chrome --remote-debugging-port=9222
```

### 第二步：登录平台

在弹出的 Chrome 窗口中，手动登录目标平台：

- 小红书：打开 https://www.xiaohongshu.com → 扫码登录
- 抖音：打开 https://www.douyin.com → 扫码登录
- 知乎：打开 https://www.zhihu.com → 扫码登录（非必须，但登录后数据更全）

> Chrome 不要关闭，最小化即可。CDP 模式下需要保持 Chrome 运行。

### 第三步：运行搜索

**Windows PowerShell：**
```powershell
$env:BROWSER_ENGINE = "cdp"

# 小红书搜索
python main.py --platform xiaohongshu --keyword "穿搭" --limit 20

# 抖音搜索
python main.py --platform douyin --keyword "AI工具" --limit 20

# 全平台并发
python main.py --platform all --keyword "美食" --limit 20
```

**macOS / Linux：**
```bash
export BROWSER_ENGINE=cdp

python main.py --platform xiaohongshu --keyword "穿搭" --limit 20
```

---

## 各平台说明

| 平台 | 命令参数 | 是否需要 CDP Chrome | 是否需要登录 |
|------|----------|:---:|:---:|
| B站 | `bilibili` | 否 | 否 |
| 小红书 | `xiaohongshu` | **是** | **是** |
| 抖音 | `douyin` | **是** | **是** |
| 知乎 | `zhihu` | 否 | 建议登录 |
| 快手 | `kuaishou` | 否 | 建议登录 |
| 微博 | `weibo` | 否 | 建议登录 |
| 贴吧 | `tieba` | 否 | 否 |

- B站：纯 HTTP，零浏览器，即开即用
- 小红书/抖音：**必须 CDP Chrome 登录**
- 其他平台：HTTP 直连，登录后数据更全

---

## AI 分析配置（可选）

开源版内置 7 个 AI Agent（趋势分析、产品挖掘、视频拆解、评论情绪、文案生成、内容改写、配图策略）。配置 LLM 后即可启用。

### 方案一：本地 Ollama（推荐，免费）

```bash
# 1. 安装 Ollama
# 下载: https://ollama.com

# 2. 拉取模型（根据显存选择）
ollama pull qwen3:14b      # 16GB 内存可用，中文最佳
# 或更轻量:
ollama pull qwen3:8b       # 8GB 内存
# 或更强:
ollama pull qwen3:32b      # 24GB+ 内存

# 3. 编辑 .env 文件
LLM_API_URL=http://localhost:11434/v1
LLM_MODEL=qwen3:14b
```

### 方案二：云端 API

```bash
# .env 文件添加（任一即可）
DEEPSEEK_API_KEY=sk-你的key      # DeepSeek，¥10 起充
# 或任何 OpenAI 兼容接口：
LLM_API_KEY=your-key
LLM_API_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

### 运行 AI 分析

```bash
python main.py --platform bilibili --keyword "AI工具" --type aggregate --pipeline full
```

> 没有配置 LLM 时搜索采集功能不受影响，仅 AI 分析自动降级为模板模式。

---

## 完整参数

```bash
python main.py --platform <平台> --keyword <关键词> --type <类型> --limit <数量>
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--platform` | 目标平台 | bilibili |
| `--keyword` | 搜索关键词 | 无 |
| `--type` | 操作类型：search / hot / detail / comment / user | search |
| `--limit` | 返回数量 | 20 |
| `--output` | 输出目录 | output/ |
| `--engine` | 引擎：playwright / cdp / langgraph | playwright |
| `--pipeline` | 分析流程：simple / full / sentiment | simple |

---

## AI 分析

开源版内置 7 个 AI Agent，配置 DeepSeek API Key 后可用：

```bash
# 编辑 .env 文件
DEEPSEEK_API_KEY=sk-你的key
DEEPSEEK_MODEL=deepseek-chat

# 运行全流程分析
python main.py --platform bilibili --keyword "AI工具" --engine langgraph --pipeline full
```

> 没有 API Key 时自动降级为模板模式，不影响搜索功能。

---

## 常见问题

**Q: 小红书/抖音搜索返回空结果？**

A: 检查以下三项：
1. CDP Chrome 是否在运行？（访问 http://127.0.0.1:9222/json/version 确认）
2. Chrome 中是否已登录小红书/抖音？
3. 是否设置了 `$env:BROWSER_ENGINE = "cdp"`？

**Q: 每次都要开 Chrome 吗？**

A: 开源版需要保持 Chrome 运行。登录一次后，只要不关 Chrome，可以一直搜索。Cookie 通常 24-48 小时过期，过期后重新扫码登录即可。

**Q: Chrome 可以关掉吗？**

A: 开源版不行。关掉 Chrome 后小红书和抖音会返回空结果。如果需要关掉 Chrome 也能搜（会话收割 + 纯 HTTP 直连），请查看 Pro 版。

**Q: 怎么确认 CDP 连接正常？**

A: 浏览器访问 http://127.0.0.1:9222/json/version ，返回 JSON 即表示 CDP Chrome 正常运行。

**Q: 搜索结果乱码？**

A: Windows PowerShell 默认 GBK 编码导致。在代码中调用或使用 JSON 输出即可正常显示中文。

---

## 目录结构

```
smart-agent/
├── main.py                  # 入口
├── src/
│   ├── agents/              # 7 平台适配器
│   ├── orchestrator/        # AI 分析引擎
│   └── utils/               # 浏览器 / 反爬 / 日志
├── scripts/
│   └── start_cdp_chrome.ps1 # CDP Chrome 启动脚本
├── output/                  # 搜索结果输出
├── browser_data/            # Cookie / Session 缓存
└── .env                     # API Key 配置
```
