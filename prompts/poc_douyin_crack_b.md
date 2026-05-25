# 路线 B：DrissionPage + CDP 破解抖音搜索翻页

## 背景

- 路线 A 结论：a_bogus 签名可以生成，但翻页有独立风控（is_load_more → verify_check），纯 HTTP 请求无解
- Python requests / curl_cffi 全被 TLS 指纹检测封杀
- 路线 B 思路：用真实浏览器做请求，拦截浏览器网络层的搜索 API 返回，唔使自己算签名

## 技术方案

DrissionPage 控制 Chromium 浏览器 → 打开抖音搜索页 → 拦截 `/aweme/v1/web/search/` 响应 → 提取数据 → 翻页（滚动加载更多 / 点「加载更多」按钮）。

## 具体步骤

### 1. 安装

```bash
pip install DrissionPage
```

### 2. 编写 `test_drission_douyin.py`

```python
"""
DrissionPage + CDP 方案 — 监听浏览器网络层，
直接截取抖音搜索 API 的响应，无需 a_bogus 签名。
"""
import time
import json
from DrissionPage import ChromiumPage, ChromiumOptions

# ── 配置 ────────────────────────────────────────
KEYWORD = "美食"
MAX_PAGES = 4
COOKIE_FILE = "output/douyin_cookies.json"  # 如有已保存 cookie

# ── Cookie 加载 ─────────────────────────────────
cookies = {}
try:
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)
except FileNotFoundError:
    pass

# ── 浏览器启动 ──────────────────────────────────
co = ChromiumOptions()
co.set_argument("--no-sandbox")
co.set_argument("--disable-blink-features=AutomationControlled")
# 如有代理：
# co.set_proxy("http://ip:port")

page = ChromiumPage(co)

# 注入 cookie
page.set.cookies(cookies)
page.get("https://www.douyin.com")
time.sleep(3)

# ── 监听搜索 API 响应 ──────────────────────────
search_results = []

def on_response(request, response):
    """拦截搜索 API 的响应"""
    url = request.url if hasattr(request, 'url') else str(request)
    if "/aweme/v1/web/search/" in url:
        try:
            body = response.body
            data = json.loads(body) if body else {}
            search_results.append({
                "url": url[:200],
                "has_more": data.get("has_more"),
                "status_code": data.get("status_code"),
                "count": len(data.get("data", [])),
            })
            print(f"  📡 拦截到搜索响应: status={data.get('status_code')}, "
                  f"items={len(data.get('data', []))}, has_more={data.get('has_more')}")
        except Exception as e:
            print(f"  ⚠️ 解析响应失败: {e}")

page.listen.response.start(targets=["aweme/v1/web/search/"], callback=on_response)

# ── 执行搜索 ────────────────────────────────────
search_url = f"https://www.douyin.com/search/{KEYWORD}?type=general"
page.get(search_url)
time.sleep(5)  # 等搜索结果加载

# ── 翻页 ────────────────────────────────────────
for i in range(MAX_PAGES):
    print(f"\n--- 尝试第 {i+2} 页 ---")

    # 方法 1: 滚动到页面底部触发加载更多
    page.scroll.to_bottom()
    time.sleep(3)

    # 方法 2: 点「加载更多」按钮（如果存在）
    try:
        load_btn = page.ele("text:加载更多", timeout=2)
        if load_btn:
            load_btn.click()
            time.sleep(3)
    except Exception:
        pass

    # 检查已有结果数
    total_items = sum(r["count"] for r in search_results)
    print(f"  目前已拦截 {len(search_results)} 个响应，共 {total_items} 条")

    if total_items >= 10 * (i + 2):
        print(f"  ✅ 第 {i+2} 页数据已获取，继续…")
    else:
        print(f"  ⚠️ 可能无更多数据或翻页失败")
        # 再试一次滚动
        page.scroll.to_bottom()
        time.sleep(3)

# ── 结果汇报 ────────────────────────────────────
print("\n" + "=" * 60)
total = sum(r["count"] for r in search_results)
print(f"拦截到 {len(search_results)} 次搜索响应，共 {total} 条数据")
print(f"翻页数: {len([r for r in search_results if r['count'] > 0])} 页")

for i, r in enumerate(search_results):
    print(f"  第 {i+1} 页: {r['count']} 条, has_more={r['has_more']}, status={r['status_code']}")

# 保存完整数据
with open("output/douyin_search_drission.json", "w", encoding="utf-8") as f:
    json.dump(search_results, f, ensure_ascii=False, indent=2)
print("数据已保存到 output/douyin_search_drission.json")

# 保持浏览器 10 秒供观察
time.sleep(10)
page.quit()
```

### 3. 运行

```bash
python test_drission_douyin.py
```

## 通过标准

- 首屏 >=10 条
- 至少 3 页，每页 >=10 条
- has_more=1 在前 2 页为 true
- 无 verify_check

## 常见问题

| 问题 | 方向 |
|------|------|
| Cookie 过期 | 打开 Chrome 登录 douyin.com → 导出 cookie 到 COOKIE_FILE |
| 滚动不触发加载 | 改点「加载更多」按钮，或用 `page.run_js("window.scrollTo(0, 99999)")` |
| 网络监听无响应 | 检查 `page.listen.response.start()` 的 targets 参数是否正确匹配 |
| TLS 还是被封 | DrissionPage 用系统 Chrome，指纹天然真实，一般不会被 TLS 封 |

## 期望产出

- ✅ 通过：完整可运行的脚本 + 3 页以上数据
- ❌ 失败：完整错误日志 + 浏览器截图
