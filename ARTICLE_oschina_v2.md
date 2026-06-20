# 开源一个月，Smart Agent 从"我自己能跑"到"社区帮我校准"

Smart Agent 是一个纯 Python、MIT 协议的多平台内容采集与分析框架。

覆盖 B站、抖音、小红书、知乎、快手、微博、贴吧 7 个平台，支持搜索、热榜、详情、评论、用户作品五种操作，内置 7 个 AI Agent 做内容分析，接上 Ollama 就能零成本跑全链路。

GitHub: https://github.com/Smart75850/smart-agent

## 和同类项目的区别

市面上不缺爬虫项目。我写这个的主要原因是我自己要用——做内容分析的时候经常需要跨平台采集数据，换平台就得换工具，体验很差。

和 MediaCrawler 相比，Smart Agent 不需要 Node.js，纯 Python 技术栈。支持 CDP 模式直接复用已登录的 Chrome，不用手动管 Cookie。内置的 AI 分析 Agent 可以接任何 OpenAI 兼容接口，包括本地 Ollama，不需要花钱调用云端 API。

## 开源第一个月，被用户教做人了

项目上线的时候我自己觉得挺稳的，每个功能都跑过，测试都绿。然后第一个用户来了。

两天之内他报了好几个 Bug，每一个我排查完之后都只能承认：确实是我代码的问题。

说几个典型的。

**环境变量被 CLI 参数默认值覆盖。** 用户设了 `BROWSER_ENGINE=cdp`，但 `main.py` 里 `args.engine` 默认值是 `playwright`，直接覆盖了用户的环境变量。这导致程序启动了一个全新的 Chrome 而不是连接用户已经登录的那个。修复很简单：环境变量没设的时候才用 CLI 参数值。

**兜底路径的代码把 property 当 method 调。** `browser.is_running` 是 `@property`，返回值是布尔。兜底搜索里写成了 `browser.is_running()`，Python 尝试把 `True` 当函数调。这个 Bug 我自己测的时候永远不会触发，因为我跑测试的时候主路径永远是成功的，走不到兜底。

**函数内 if 分支里 import 导致 UnboundLocalError。** 我在 `if args.type == "aggregate"` 分支里写了一个局部 `from config.settings import settings`。Python 的规则是函数内任何位置有 import 或赋值，整个函数都会把那个名字当局部变量。用户没走这个分支，`settings` 从未被局部赋值，后面用到的时候就炸了。而我"自己"跑的时候一定会走 aggregate 路径，所以完全没发现。

**正文提取只刮到 13 个字。** CSS 选择器刮不到小红书帖子的正文——数据藏在 `window.__INITIAL_STATE__` 这个 SSR 内嵌变量里。现代前端框架的数据经常不在 DOM 里，得先看 JS 全局变量。

**搜索和热榜返回的数据结构不一致。** 搜索用 API 拦截拿 15 个字段，热榜用 DOM 兜底只拿 4 个。兜底的时候我只求不崩，没管字段对齐。但用户不知道哪个是主路径哪个是兜底，在他眼里都是同一个功能。

## 开源维护者的一些碎碎念

修完这些 Bug 之后我在项目文档里加了一条"Failure Path 测试标准"——每次写完代码至少测三个失败场景。你的环境完美不代表用户的环境也完美，这件事听起来很废话，但真的写到代码里就很容易忘。

还有就是认真回 Issue。那个用户虽然没付钱，但他帮我做了花钱都买不到的测试——在完全陌生的环境里，用我完全没想到的方式，把我的代码从头到尾跑了一遍。每一个 Bug 报告都是一份免费的 QA 报告。

最后是一个很实操的建议：给你的项目写一个懒人包。一个 `.bat` 文件，用户双击就能跑，不用手打任何命令。很多用户不是不会用，是懒得看文档。你把门槛降到最低，用的人就多了。

## 试试看

```bash
git clone https://github.com/Smart75850/smart-agent.git
cd smart-agent
pip install -r requirements.txt
playwright install chromium

# 搜索
set BROWSER_ENGINE=cdp
python main.py --platform xiaohongshu --keyword "穿搭"

# 搜完自动拉详情正文
python main.py --platform xiaohongshu --keyword "穿搭" --limit 5 --fetch-detail
```

装个 Ollama 就能跑 7 个 AI Agent，不花一分钱。

---

项目 MIT 协议开源，欢迎提 Issue、PR、Star。

GitHub: https://github.com/Smart75850/smart-agent
