# 我的开源项目上线一个月，用户帮我测出 15 个 Bug，我学到的 6 个教训

> 一个真实的开源项目成长记录：从「我自己跑得通啊」到「用户什么都跑不通」。

---

Smart Agent 上线 GitHub 快一个月了。7 平台内容采集、CDP 浏览器复用登录态、本地 Ollama 跑 7 个 AI Agent 分析——听着很美好。

然后用户来了。然后 Bug 来了。然后我意识到：**我自己测的那叫演示，用户用的那才叫测试。**

这篇文章记录过去 48 小时内，一个用户帮我发现并修复的 15+ 个问题，以及我从中学到的 6 个教训。如果你也在维护开源项目，或者准备把自己的工具开源，这些经验应该对你有用。

---

## 项目简介

Smart Agent 是一个多平台内容采集框架，纯 Python，支持 B站、抖音、小红书、知乎、快手、微博、贴吧 7 个平台的搜索、热榜、详情、评论采集。内置 7 个 AI Agent，可以接本地 Ollama 或任何 OpenAI 兼容接口做爆款分析、选品挖掘、评论情绪、文案生成等。

GitHub: https://github.com/Smart75850/smart-agent

---

## Bug 1：「我设了 CDP 模式，但它还是弹出了新 Chrome」

这是用户遇到的第一个问题，也是最致命的一个。

用户按照文档，先启动了 CDP Chrome（`--remote-debugging-port=9222`），设了环境变量 `BROWSER_ENGINE=cdp`，然后运行搜索。结果——程序弹出了一个全新的 Chrome 窗口，而不是连接他已经登录的那个。

**根因**：`main.py` 里有这么一行：

```python
os.environ["BROWSER_ENGINE"] = args.engine  # args.engine 默认值 = "playwright"
```

无论用户设没设环境变量，这行代码都会用命令行参数的默认值 `playwright` 覆盖掉。用户的 `cdp` 设置被无声无息地改回了 `playwright`，自然就启动了新浏览器。

**教训 ①：CLI 参数和环境变量的优先级要搞对。** 用户设了环境变量就应该尊重，不要用默认参数去覆盖。修复很简单：

```python
if "BROWSER_ENGINE" not in os.environ:
    os.environ["BROWSER_ENGINE"] = args.engine
```

---

## Bug 2：「它报了 'bool' object is not callable」

用户设置好 CDP 模式后，搜索返回空结果（因为没有登录小红书），然后程序进入兜底搜索路径，接着就崩了。

错误信息是：`'bool' object is not callable`。

**根因**：`browser_service.py` 里 `is_running` 是一个 `@property`：

```python
@property
def is_running(self) -> bool:
    return self._browser is not None
```

但在兜底搜索函数里，有人写了 `browser.is_running()`——加了括号。Python 把 `is_running` 返回的 `True` 当成函数来调用，于是 `True()` → `'bool' object is not callable`。

**教训 ②：property 和 method 的调用方式不一样，Code Review 时要留意。** Python 不会在定义时告诉你「这个属性将来可能被当方法调用」，只会在运行时炸。

---

## Bug 3：「搜是搜到了，但保存的时候报错」

用户搜索成功，拿到了 40 条小红书结果。然后程序在保存结果时崩溃了：

```
UnboundLocalError: cannot access local variable 'settings' where it is not associated with a value
```

**根因**：之前在 `main()` 函数里加 API Key 检测功能时，在 `if` 分支里写了：

```python
if args.type == "aggregate":
    from config.settings import settings  # ← 埋雷
```

问题在于 Python 的作用域规则：**函数内任何位置出现 `import xxx` 或 `xxx = ...`，整个函数都会把 `xxx` 当作局部变量。** 用户没有用 `--type aggregate`，那个 `if` 分支没有执行，`settings` 从未被赋值——但 Python 仍然认为它是局部变量。函数后面用到 `settings.STORE_BACKEND` 时，就报了 `UnboundLocalError`。

而模块顶部明明已经 `from config.settings import settings` 了，这个 `if` 里的重复 import 完全是多余的。

**教训 ③：不要在函数内部的 if 分支里 import 模块级已导入的东西。** 要 import 就放函数顶部，或者直接引用已有的模块级变量。

---

## Bug 4：「详情内容不对，只有 13 个字」

用户搜索成功后，用 `--type detail` 拉取帖子正文，结果 `desc` 字段只返回了 13 个字：「发现RED直播发布通知我我」。

**根因**：最初的详情提取是用 CSS 选择器从 DOM 刮数据，但小红书把真正的帖子正文藏在了 `window.__INITIAL_STATE__` 这个 SSR 内嵌的 JavaScript 变量里，DOM 上只是一个残缺的预览。

解决方法是直接从 `__INITIAL_STATE__.note.noteDetailMap[noteId].note` 提取数据——标题、正文（752 字）、作者、点赞收藏评论数、图片列表、标签、发布时间、IP 属地，全部齐了。

**教训 ④：现代 SPA/SSR 页面的数据源不在 DOM 里，在 JS 变量里。** 先打开浏览器 DevTools，在 Console 里敲 `window.__INITIAL_STATE__`，看看数据到底在哪，再写选择器。

---

## Bug 5：「格式不一致——搜索返回到的数据和热榜返回到的不一样」

早期版本中，搜索用 API 拦截返回完整字段（note_id、xsec_token、url、cover_url、image_count），但 DOM 兜底和热榜只返回 title、author、likes、link 四个字段。用户用搜索结果能正常查看详情，用热榜结果就不行。

**根因**：我写代码时重点是「主路径能跑通」，兜底路径只求「不崩溃」。但用户的实际使用中，API 拦截可能失败（网络波动、反爬升级等），兜底路径被调用的频率比我想象的高很多。

**教训 ⑤：兜底路径的数据格式必须和主路径对齐。** 主路径返回什么字段，兜底路径就应该返回什么字段（至少 key 一致，值可以为空）。不能主路径 15 个字段、兜底路径 4 个字段。

---

## 非技术教训

### 教训 ⑥：用户帮你做的测试，比你自己做的全面 10 倍

我自己测试的时候，CDP Chrome 已登录、网络正常、API 拦截成功、LLM Key 已配置——全是 Happy Path。

用户的环境是：CDP Chrome 开了但没登录小红书、Windows cmd 设环境变量、网络延迟导致 API 拦截偶尔失败、没有配置 LLM API Key——全是 Edge Case。

**我做的是演示，用户做的是测试。**

现在我的项目文档里多了一条「测试铁律」——每次写完代码，至少测 3 条 Failure Path：
- 环境变量未设/设错
- API 拦截失败 → DOM 兜底
- 登录态缺失
- Python 版本差异
- Windows cmd 和 PowerShell 语法差异

---

## 项目后续规划

经过这轮 Bug 修复，开源版已经比较稳定了。接下来的计划：

1. **Python 3.9+ 兼容**（目前已兼容）
2. **更多 Failure Path 的自动化测试**
3. **Pro 版**：定期发布包含 Session 收割、纯 HTTP 直连、Docker 部署、WebUI 等进阶功能的版本

---

## 总结

开源一个月，最大感受：**把代码开源只是开始，真正的产品是用户使用之后的那个版本。**

如果你也在做开源项目，建议：

1. **先写好懒人包**——一个 `.bat` 文件，用户双击就能跑，不要让他手打环境变量
2. **让用户帮你找 Bug**——认真回每一个 Issue，那是免费的 QA
3. **测 Failure Path，不要只测 Happy Path**——你的环境完美 ≠ 用户的环境完美
4. **写文章记录**——每一个 Bug 都是一篇好内容

---

*GitHub: https://github.com/Smart75850/smart-agent*

*欢迎 Star、Issue、PR。如果你在用过程中遇到任何问题，开 Issue 我会尽快回复。*
