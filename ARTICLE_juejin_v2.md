# 开源一个月，我的7平台爬虫被用户测出了15个Bug，修复过程全记录

> 一个真实开源项目的成长故事：从「我自己跑得通啊」到「对不起，是我的锅」。

---

Smart Agent 上线 GitHub 快一个月了——一个纯 Python 的多平台内容采集框架，覆盖 B站/抖音/小红书/知乎/快手/微博/贴吧 7 个平台，内置 7 个 AI Agent，接上 Ollama 或任意 OpenAI 接口就能自动做爆款分析、选品挖掘、评论情绪、文案生成。

GitHub: https://github.com/Smart75850/smart-agent

听着很美好对吧？

然后用户来了。然后 Bug 来了。然后我意识到：**我自己测的是演示，用户用的才是测试。**

这篇文章没有「我如何从零构建一个爬虫框架」的宏观叙事，只有 48 小时内被用户报出来的 5 个真实 Bug 以及修复过程。如果你也在做 Python 项目、或者在维护开源工具，这些坑你应该都会遇到。

---

## Bug 1：环境变量被无声覆盖，CDP 模式根本没生效

**现象**：用户设了 `BROWSER_ENGINE=cdp`，CDP Chrome 也在 9222 端口跑着，但程序还是弹出了一个全新的 Chrome 窗口，而不是连接他已经登录的那个。

**排查**：用户怀疑自己设错了环境变量，反复确认语法没问题。我检查代码后发现——

```python
# main.py — 旧代码
os.environ["BROWSER_ENGINE"] = args.engine
# args.engine 默认值是 "playwright"
```

`--engine` 参数的默认值是 `playwright`。即使用户已经 `set BROWSER_ENGINE=cdp` 了，`main.py` 照样用 `playwright` 覆盖掉。用户的 `cdp` 设置被无声无息地抹杀了。

**修复**：

```python
if "BROWSER_ENGINE" not in os.environ:
    os.environ["BROWSER_ENGINE"] = args.engine
```

**教训**：CLI 参数默认值和环境变量的优先级要想清楚。我的规则是——**用户显式设了环境变量，就不要用参数默认值去覆盖。**

---

## Bug 2：`'bool' object is not callable` — Property 被当成了 Method

**现象**：搜索返回空结果后，程序走兜底路径时崩了，报错 `'bool' object is not callable`。

**排查**：`browser_service.py` 里 `is_running` 是个 `@property`：

```python
@property
def is_running(self) -> bool:
    return self._browser is not None
```

但在 `_adaptive_search` 兜底函数里，写成了 `browser.is_running()`——加了对括号。

Python 把 `is_running` 返回的 `True`（bool 值）当成函数来调用，于是 `True()` → `'bool' object is not callable`。

**修复**：`browser.is_running()` → `browser.is_running`，去掉括号。

**教训**：`@property` 和普通方法的调用语法不一样。Python 不会在定义时提示你「这个属性将来可能被当方法调用」，只在运行时炸。Code Review 时特别注意属性访问有没有多余的括号。

---

## Bug 3：搜是搜到了，保存时 UnboundLocalError

**现象**：用户搜索小红书拿到了 40 条结果，但在保存输出时崩了：

```
UnboundLocalError: cannot access local variable 'settings'
```

**排查**：`main()` 函数里之前加 API Key 检测时，在 `if` 分支里写了：

```python
if args.type == "aggregate":
    from config.settings import settings  # ← 埋雷
```

**Python 作用域规则**：函数内任何位置出现 `import xxx` 或 `xxx = ...`，整个函数都会把 `xxx` 当作局部变量。用户没有用 `--type aggregate`，`if` 分支不执行，`settings` 从未被局部赋值——但 Python 仍然认为它是局部变量。后面 `settings.STORE_BACKEND` 就报了 `UnboundLocalError`。

**修复**：删掉 `if` 里的重复 import（模块顶部已经 import 过了）。

**教训**：不要在函数内部的 `if` 分支里 import 模块级已导入的东西。这属于「怎么写都不会想到会炸，但确实会炸」的 Python 坑。

---

## Bug 4：详情内容只返回了 13 个字

**现象**：用户搜到帖子后用 `--type detail` 拉取正文，`desc` 字段只返回了 13 个字：「发现RED直播发布通知我我」。正文完全不匹配。

**排查**：最初的详情提取逻辑是用 CSS 选择器从 DOM 刮数据，`querySelector('.desc')` 之类的。但小红书把真正的帖子正文藏在了 SSR 内嵌的 JS 变量里——`window.__INITIAL_STATE__`。这个变量包含了帖子的完整数据：标题、正文（752 字）、作者、头像、互动数据、图片列表、标签、发布时间、IP 属地……而 DOM 里只有一个残缺的预览。

**修复**：提取逻辑改为优先读 `__INITIAL_STATE__.note.noteDetailMap[noteId].note`，DOM 作为兜底。

```javascript
const state = window.__INITIAL_STATE__;
const note = state.note.noteDetailMap[noteId].note;
// 现在标题、正文、图片、标签全有了
```

**教训**：现代 SPA/SSR 页面的数据源不在 DOM 里，在 JS 变量里。写爬虫的时候，先打开 DevTools Console，敲 `window.__INITIAL_STATE__`（或者 `__NEXT_DATA__`、`__NUXT__`、`__SVELTEKIT__`——框架不同名字不同），看看数据到底在哪，再决定用 CSS 选择器还是 JS 变量。

---

## Bug 5：API 拦截和 DOM 兜底的数据格式不一致

**现象**：搜索和热榜返回的字段不一样。搜索有 `note_id`、`xsec_token`、`url`、`image_count`，热榜只有 `title`、`author`、`likes`、`link`。用户用搜索结果能正常看详情，用热榜结果就不行——因为热榜结果缺少 `xsec_token`。

**排查**：搜索用的是 API 拦截（`page.on("response")`），能拿到完整的 API 响应数据。热榜只有 DOM 兜底，CSS 选择器只能刮到 4 个字段。两个路径返回的数据结构完全不同，下游代码处理时就会炸。

**修复**：给热榜也加了 API 拦截（拦截 `/api/sns/web/v1/homefeed`），DOM 兜底也升级成跟 API 一致的字段名和结构。现在所有入口（搜索、热榜、用户主页）返回的数据结构完全一致。

**教训**：兜底路径的数据格式必须和主路径对齐。主路径返回什么字段，兜底路径就应该返回什么字段（至少 key 一致，值可以为空）。

---

## 非技术总结

### 我的最大收获：用户做的才是测试

我自己测试的时候：CDP Chrome 已登录、网络正常、API 拦截成功——全是 Happy Path。用户的环境：CDP Chrome 开了但没登录、Windows cmd 手打环境变量、网络延迟导致拦截失败——全是 Edge Case。

现在我的项目里多了一条**「Failure Path 测试铁律」**——每次写完代码，至少测 3 条失败路径：

| Failure Path | 必测 |
|---|---|
| 环境变量未设 / 设错 | ✅ |
| API 拦截失败 → DOM 兜底 | ✅ |
| 登录态缺失 | ✅ |
| 用户 cmd 语法 vs PowerShell 语法 | ✅ |
| Python 版本 3.9 vs 3.11+ | ✅ |

---

## 项目现状

经过这轮修复，开源版已比较稳定。如果你想试试：

```bash
git clone https://github.com/Smart75850/smart-agent.git
cd smart-agent
pip install -r requirements.txt

# 懒人包：双击 scripts\quick_xhs.bat，自动启动 CDP Chrome + 提示登录 + 搜索
# 或者手打：
set BROWSER_ENGINE=cdp
python main.py --platform xiaohongshu --keyword "穿搭"
```

接上本地 Ollama 就能跑 7 个 AI Agent 全链路分析（`ollama pull qwen3:14b`），一分钱不花。

---

*GitHub: https://github.com/Smart75850/smart-agent*

*Star ⭐ 是对开源作者最好的鼓励。有问题直接提 Issue，看到就会回。*
