# 开源一个月，我的7平台爬虫被用户测出了15个Bug

Smart Agent 上线 GitHub 快一个月了。一个纯 Python 的多平台内容采集框架，支持 B站、抖音、小红书、知乎、快手、微博、贴吧，内置了 7 个 AI Agent，接上 Ollama 或者任意 OpenAI 接口就能自动做爆款分析、选品挖掘、评论情绪、文案生成。

GitHub: https://github.com/Smart75850/smart-agent

听着挺美好的。然后用户来了，然后 Bug 来了。我才意识到自己写的代码到底有多脆。

这篇文章不讲什么「从零构建爬虫框架」的宏大叙事，就是实打实记录一下过去两天被用户报出来的几个 Bug，以及修的过程中踩的坑。如果你也在做 Python 项目或者维护开源工具，应该会遇到类似的问题。

## Bug 1：环境变量被默默覆盖了

用户说他设了 `BROWSER_ENGINE=cdp`，CDP Chrome 也在 9222 端口跑着，但程序还是弹了一个全新的 Chrome 窗口出来，根本没连接他已经登录的那个。

排查了一圈发现，`main.py` 里有这么一行：

```python
os.environ["BROWSER_ENGINE"] = args.engine
```

`--engine` 参数的默认值是 `playwright`。也就是说，不管用户有没有设环境变量，这行代码都会用默认值 `playwright` 覆盖掉。用户的 `cdp` 设置被无声无息地抹掉了。

修复就一行：

```python
if "BROWSER_ENGINE" not in os.environ:
    os.environ["BROWSER_ENGINE"] = args.engine
```

这事说起来不复杂，但用户因为这个折腾了快一个小时。一个参数默认值搞出来的问题，完全是我的责任。

## Bug 2：`'bool' object is not callable`

搜索返回空结果（用户还没登录小红书），程序走兜底路径的时候崩了，报错 `'bool' object is not callable`。

原因：`browser_service.py` 里 `is_running` 是个 `@property`，返回值是布尔。但兜底搜索函数里写成了 `browser.is_running()` —— 多了对括号。Python 尝试把 `True` 当函数调，于是炸了。

这个 Bug 我自己测的时候根本触发不了，因为我跑测试的时候不会走到兜底路径——永远是主路径成功，永远用不到那个 fallback 函数。用户一跑就踩到了。

把括号去掉就修好了。

## Bug 3：搜到数据了，保存的时候崩了

这个是最让我脸上挂不住的。

用户搜小红书拿到了 40 条结果，然后在保存输出的时候程序崩了：

```
UnboundLocalError: cannot access local variable 'settings'
```

我之前在 `main()` 函数里加 API Key 检测功能的时候，在一个 `if` 分支里写了：

```python
if args.type == "aggregate":
    from config.settings import settings
```

Python 的作用域规则是这样的：函数内任何位置出现 `import xxx` 或者 `xxx = ...`，整个函数都会把 `xxx` 当局部变量。用户没有用 `--type aggregate`，那个 `if` 分支没执行到，`settings` 局部变量从未被赋值，但 Python 仍然认为它是局部变量。后面代码里用到 `settings.STORE_BACKEND` 的时候直接就 UnboundLocalError 了。

而模块顶部明明已经 `from config.settings import settings` 过了，这个 `if` 里的重复 import 完全是多余的。删掉就好。

这个坑说实话挺反直觉的，我自己写的时候完全没意识到会有问题——因为「我自己」跑的时候一定是走 aggregate 路径的。

## Bug 4：正文只返回了 13 个字

用户搜到帖子后用 `--type detail` 拉取正文，`desc` 字段只返回了 13 个字：「发现RED直播发布通知我我」。内容完全不对。

原因是我最初的详情提取是用 CSS 选择器刮 DOM 的，`querySelector('.desc')` 之类的。但小红书把真正的帖子正文藏在 `window.__INITIAL_STATE__` 这个 SSR 内嵌的 JS 变量里，里面有标题、正文（752 字）、作者、头像、互动数据、图片列表、标签、发布时间、IP 属地。DOM 里只有一个残缺的预览。

改成优先读 `__INITIAL_STATE__` 就好了。现在详情能拿到完整的 15 个字段。

这个 Bug 让我意识到，写爬虫的时候不能只看 DOM。现代前端框架的数据经常不在 HTML 里，得先打开 DevTools Console 看看 `window.__INITIAL_STATE__` 这类全局变量。

## Bug 5：搜索和热榜返回的数据结构对不上

搜索用的是 API 拦截（`page.on("response")`），能拿到完整的 15 个字段。热榜只有 DOM 兜底，CSS 选择器只能刮到 4 个字段。两个路径返回的东西完全不同，下游代码处理的时候就乱了——用户从搜索结果能正常看详情，从热榜结果就不行，因为缺了 `xsec_token`。

写兜底路径的时候我只求「不崩溃」，没考虑到数据格式要对齐主路径。但用户不知道什么路径是主什么路径是兜底，对他来说都是同一个功能。

修的方式是给热榜也加上 API 拦截，DOM 兜底也补全字段。现在所有入口返回的数据结构完全一致了。

## 写代码的以为自己测过了，用户一跑才知道没测

我自己测的时候：CDP Chrome 已登录、网络正常、API 拦截每次都成功、LLM Key 配好了。全是 happy path。

用户的环境：CDP Chrome 开了但没登录、Windows cmd 手打环境变量、网络偶尔延迟导致 API 拦截失败、没配 API Key 所以走兜底路径。全是 edge case。

说白了，我做的叫演示，用户做的才叫测试。

现在我在项目里加了一条硬性要求：每次写完代码，至少测三条失败路径——环境变量没设或者设错了会怎样、API 拦截失败走 DOM 兜底会怎样、没登录的时候会怎样。

这套标准以后也适用我所有的项目。

## 试试看

```bash
git clone https://github.com/Smart75850/smart-agent.git
cd smart-agent
pip install -r requirements.txt

# Windows 懒人包：双击 scripts\quick_xhs.bat
# 或者手打：
set BROWSER_ENGINE=cdp
python main.py --platform xiaohongshu --keyword "穿搭"

# 搜完自动拉详情正文
python main.py --platform xiaohongshu --keyword "穿搭" --limit 5 --fetch-detail
```

装个 Ollama（`ollama pull qwen3:14b`），改一下 `.env` 就能跑 7 个 AI Agent 做全链路分析，不花一分钱。

GitHub: https://github.com/Smart75850/smart-agent

有问题直接提 Issue，看到就会回。Star 是对开源作者最好的鼓励。
