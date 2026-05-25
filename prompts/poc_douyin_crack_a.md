# 任务：跑通抖音搜索 a_bogus 签名 PoC

## 你要做什么（一句话）

用 execjs 调用 bdms.js 对抖音搜索 API 做签名，确认能翻 3 页以上。

---

## Step 1：装两个包

```bash
pip install pyexecjs curl_cffi
```

## Step 2：下载 bdms.js

从这里下载：
- https://github.com/zycheung/douyin_sign （找编译好的 bdms.js，约 10 万行）

下载后放到项目根目录：`src/utils/bdms.js`

## Step 3：抓一套抖音 Cookie

浏览器打开 `douyin.com` → F12 → Network → 随便点一个请求 → Request Headers → 把 Cookie 整行复制下来。

最少要有这四个字段：`msToken`、`ttwid`、`odin_tt`、`ttcid`，缺一个就会被识别为机器人。

## Step 4：跑下面这个脚本

在项目根目录创建并运行 `test_douyin_sign.py`：

```python
"""
抖音搜索 a_bogus 签名 PoC
用法：先填好 COOKIES 和 BDMS_PATH，然后 python test_douyin_sign.py
"""
import execjs
import json
import time
from urllib.parse import urlencode
from curl_cffi import requests as curl_requests

# ═══════════════════════════════════════════════════════════════
# 配置（改这三处就能跑）
# ═══════════════════════════════════════════════════════════════
BDMS_PATH = "src/utils/bdms.js"

COOKIES = {
    "msToken": "填你的",
    "ttwid": "填你的",
    "odin_tt": "填你的",
    "ttcid": "填你的",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Referer": "https://www.douyin.com/",
}

KEYWORD = "美食"          # 搜什么
MAX_PAGES = 4             # 测几页

# ═══════════════════════════════════════════════════════════════
# 加载 bdms.js
# ═══════════════════════════════════════════════════════════════
print(f"加载: {BDMS_PATH}")
with open(BDMS_PATH, "r", encoding="utf-8") as f:
    source = f.read()

ctx = execjs.compile(source)
print("编译 OK")

# ═══════════════════════════════════════════════════════════════
# 签名函数（自动匹配 bdms.js 暴露的函数名）
# ═══════════════════════════════════════════════════════════════
def sign_url(url: str) -> str:
    names = ["sign_url", "get_a_bogus", "getABogus", "sign"]
    for name in names:
        try:
            if name == "get_a_bogus":
                result = ctx.call(name, url, HEADERS["User-Agent"])
            else:
                result = ctx.call(name, url)
            if result and len(str(result)) > 10:
                return str(result)
        except Exception:
            continue
    raise RuntimeError(f"所有签名函数都失败，试了: {names}")

# ═══════════════════════════════════════════════════════════════
# 翻页测试
# ═══════════════════════════════════════════════════════════════
print(f"\n开始搜索: {KEYWORD}")
print("=" * 60)

ok_pages = 0
for page in range(MAX_PAGES):
    offset = page * 10

    # 构造 URL
    params = {
        "keyword": KEYWORD, "offset": offset, "count": 10,
        "aid": 6383, "channel": "search_result",
        "search_source": "normal_search_suggest",
        "query_correct_type": 1, "is_filter_search": 0,
    }
    url = "https://www.douyin.com/aweme/v1/web/search/item/?" + urlencode(params)

    # 签名
    signed = sign_url(url)

    # 发请求
    resp = curl_requests.get(signed, headers=HEADERS, cookies=COOKIES,
                             impersonate="chrome120", timeout=15)
    data = resp.json()

    # 看结果
    sc = data.get("status_code")
    hm = data.get("has_more")
    items = data.get("data", []) or data.get("aweme_list", [])
    n = len(items)

    print(f"  page {page+1} (offset={offset}): status_code={sc}, has_more={hm}, items={n}")

    if sc == 0 and n >= 10:
        ok_pages += 1
        # 打印前两条看下内容
        for item in items[:2]:
            info = item.get("aweme_info", {}) or item
            desc = info.get("desc", "")[:60]
            nickname = info.get("author", {}).get("nickname", "")
            print(f"    - {nickname}: {desc}")
    else:
        print(f"    ❌ 失败，完整返回：")
        print(json.dumps(data, ensure_ascii=False, indent=2)[:800])
        break

    time.sleep(2)  # 别太快

# ═══════════════════════════════════════════════════════════════
# 结论
# ═══════════════════════════════════════════════════════════════
print("=" * 60)
if ok_pages >= 3:
    print(f"✅ 通过：{ok_pages}/{MAX_PAGES} 页正常")
else:
    print(f"❌ 不通过：只有 {ok_pages}/{MAX_PAGES} 页正常")
```

## 期望结果

- **通过**：status_code=0，每页 10+ 条，has_more=1，至少 3 页
- **不通过**：把控制台完整输出贴给我（不要省略）

---

## 可能遇到的问题 & 怎么修

| # | 现象 | 解决 |
|---|------|------|
| 1 | `execjs` 报 `window is not defined` | 在 `with open...` 之后、`source = f.read()` 之后加：`source = "var window = {}; var document = {}; var navigator = {userAgent: '" + HEADERS['User-Agent'] + "'}; var location = {href: 'https://www.douyin.com/'};\\n" + source` |
| 2 | status_code 不是 0 | Cookie 不完整，去浏览器重新抓。确保 msToken / ttwid / odin_tt / ttcid 都在 |
| 3 | 第一页 OK 但第二页挂了 | a_bogus 每次都要重新生成，确认你的 sign_url 函数每次都在调 |
| 4 | `impersonate` 报错 | 降级用普通 `requests` 替代 `curl_requests`，先验证签名算法本身 |
| 5 | bdms.js 函数名对不上 | 打开 bdms.js 搜 `function sign` 或搜 `a_bogus`，看实际暴露了什么函数 |

---

## Checklist（做完打勾）

- [ ] pip install pyexecjs curl_cffi 成功
- [ ] bdms.js 已下载到 src/utils/bdms.js
- [ ] Cookie 已从浏览器抓取填入 COOKIES
- [ ] 脚本能跑，没有 import / 编译 / Cookie 错误
- [ ] 第 1 页 status_code=0，10 条
- [ ] 第 2 页正常
- [ ] 第 3 页正常
- [ ] 第 4 页正常
- [ ] 全部通过 → 交出完整脚本和 bdms.js
- [ ] 任何失败 → 交出完整控制台日志
