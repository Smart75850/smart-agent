# 开源一个月，社区用户帮我找出 15 个 Bug——Smart Agent 真实成长记录

> 一个 MIT 协议的多平台内容采集框架，从"我自己跑得通"到"社区帮我校准"的 30 天。

---

## 项目简介

Smart Agent 是一个纯 Python、MIT 开源协议的多平台内容采集与分析框架。

- **7 个平台**：B站、抖音、小红书、知乎、快手、微博、贴吧
- **5 种操作**：关键词搜索、热榜、帖子详情、评论采集、用户作品
- **7 个 AI Agent**：爆款识别、选品分析、视频拆解、评论情绪、文案生成、内容改写、配图策略（支持本地 Ollama 或任何 OpenAI 兼容接口，零成本可用）
- **6 种存储**：JSON、CSV、JSONL、Excel、SQLite、MySQL
- **零 Node.js 依赖**：纯 Python 技术栈

GitHub: https://github.com/Smart75850/smart-agent

---

## 为什么又写了一个采集框架

市面上不缺爬虫工具，但缺一个**对 Python 技术栈友好、多平台统一接口、能复用浏览器登录态**的方案。

| 对比 | MediaCrawler | Smart Agent |
|---|---|---|
| 技术栈 | Python + Node.js | 纯 Python |
| 平台数 | 7+ | 7 |
| CDP 复用登录 Chrome | ❌ | ✅ |
| AI 分析 Agent | ❌ | ✅ 7 个 Agent |
| 本地 LLM 支持 | ❌ | ✅ Ollama 零成本 |
| MCP 协议 | ❌ | ✅ |
| 开源协议 | Apache-2.0 | MIT |

---

## 从"线上可用"到"线下稳定"：5 个真实的 Bug 修复记录

### Bug 1：环境变量被 CLI 参数默认值覆盖

用户设了 `BROWSER_ENGINE=cdp`，但 `main.py` 里 `args.engine` 默认值是 `playwright`，直接覆盖了用户的环境变量。导致程序启动了新浏览器而不是连接 CDP Chrome。

> 修复：只有环境变量未设时才用 CLI 参数值。

### Bug 2：Property vs Method 混淆

`browser.is_running` 是 `@property`，但兜底代码写成了 `browser.is_running()`——把 `True` 当函数调用。

> 修复：去掉括号。`@property` 返回的是值，不是 callable。

### Bug 3：if 分支内 import 导致 UnboundLocalError

在 `if args.type == "aggregate"` 分支里写了 `from config.settings import settings`，导致 Python 将 `settings` 视为整个函数的局部变量。用户没走这个分支时，后面 `settings.STORE_BACKEND` 就炸了。

> 修复：删掉重复 import，直接使用模块顶部的导入。

### Bug 4：详情正文只返回 13 个字

CSS 选择器刮不到小红书的正文——数据藏在 SSR 内嵌的 `window.__INITIAL_STATE__` 变量里。

> 修复：优先从 `__INITIAL_STATE__` 提取，DOM 作为兜底。

### Bug 5：主路径和兜底路径数据结构不一致

API 拦截返回 15 个字段，DOM 兜底只返回 4 个。下游代码处理时无法统一。

> 修复：所有入口统一数据结构，兜底路径补全字段。

---

## 对开源维护者的 6 条建议

1. **写懒人包**——一个 `.bat` 文件，用户双击就能跑，不要让他手打环境变量
2. **用户是免费的 QA 团队**——认真回每一个 Issue，那是你花钱都买不到的测试覆盖
3. **测 Failure Path**——你的环境完美 ≠ 用户的环境完美
4. **环境变量优先于默认参数**——用户显式设置的，不要用代码默认值覆盖
5. **兜底路径数据格式要对齐主路径**——不能主路径 15 字段、兜底 4 字段
6. **现代 SPA 的数据在 JS 变量里**——写采集逻辑前，先看 `window.__INITIAL_STATE__`

---

## 社区参与

项目完全开源（MIT License），欢迎任何形式的贡献：

- 🐛 **提交 Bug**：GitHub Issues
- 📝 **完善文档**：README、Wiki、使用指南
- 🔧 **贡献代码**：Fork → PR → Review
- ⭐ **Star**：对项目最大的认可

---

*GitHub: https://github.com/Smart75850/smart-agent*

*如果你也在做内容采集或数据分析相关的工具，欢迎交流。*
