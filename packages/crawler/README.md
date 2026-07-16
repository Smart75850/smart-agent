# Smart Crawler

多平台内容采集，纯 Python。7 平台一行 import 即刻用得。

## 安装

```bash
pip install -e packages/crawler/
```

## 快速开始

```python
import asyncio
from smart_crawler import search, start_browser, close_browser

async def main():
    await start_browser(engine="cdp")  # 连接已登录的 CDP Chrome

    # 一行搜
    items = await search("xiaohongshu", "穿搭", limit=10)
    for item in items:
        print(item["title"], item["url"])

    await close_browser()

asyncio.run(main())
```

## 平台专有类

```python
from smart_crawler import XiaohongshuCrawler, BilibiliCrawler

xhs = XiaohongshuCrawler()
items = await xhs.search("AI", limit=20)
detail = await xhs.detail(items[0]["note_id"], xsec_token=items[0]["xsec_token"])

bili = BilibiliCrawler()
items = await bili.search("Python")  # B站无需浏览器
```

## 支持的平台

| 平台 | 类名 | 搜索 | 热榜 | 详情 | 评论 | 用户 |
|------|------|:---:|:---:|:---:|:---:|:---:|
| B站 | BilibiliCrawler | ✅ | ✅ | ✅ | ✅ | ✅ |
| 小红书 | XiaohongshuCrawler | ✅ | ✅ | ✅ | ✅ | ✅ |
| 抖音 | DouyinCrawler | ✅ | ✅ | ✅ | ✅ | ✅ |
| 知乎 | ZhihuCrawler | ✅ | ✅ | ✅ | ✅ | ✅ |
| 快手 | KuaishouCrawler | ✅ | ✅ | ✅ | ✅ | ✅ |
| 微博 | WeiboCrawler | ✅ | ✅ | ✅ | ✅ | ✅ |
| 贴吧 | TiebaCrawler | ✅ | ✅ | ✅ | ✅ | ✅ |
