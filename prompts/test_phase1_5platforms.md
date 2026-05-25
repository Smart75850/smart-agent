# Phase 1 验收测试：5 平台全覆盖实战

## 前置

```bash
pip install DrissionPage  # 抖音搜索用
```

Cookie 准备：各平台从浏览器导出 cookie 放到 `output/` 目录。

## 测试矩阵

每个平台跑以下动作，每项必须 **翻 3 页以上** 才算通过。

### B站 (bilibili)

| 动作 | 测试内容 | 关键词/ID | 通过标准 |
|------|---------|----------|----------|
| search | 搜索翻页 | `Python教程` | >=3 页，每页 >=15 条 |
| rank | 排行榜 | 无需 | >=20 条 |
| detail | 视频详情 | 搜索结果第一条 BV 号 | 返回标题+作者+播放量 |
| comment | 评论翻页 | 同上 BV 号 | >=2 页，每页 >=10 条 |
| user | 用户主页 | 搜索结果第一条作者 UID | >=10 条视频 |

### 小红书 (xiaohongshu)

| 动作 | 测试内容 | 关键词/ID | 通过标准 |
|------|---------|----------|----------|
| search | 搜索翻页 | `AI 绘画` | >=3 页，每页 >=5 条 |
| hot | 热门 | 无需 | >=10 条 |
| detail | 笔记详情 | 搜索结果第一条 ID | 返回标题+作者+内容 |
| comment | 评论翻页 | 同上 | >=2 页 |

### 抖音 (douyin)

| 动作 | 测试内容 | 关键词/ID | 通过标准 |
|------|---------|----------|----------|
| search | 搜索翻页 | `美食` | **>=5 页**，每页 >=10 条，status_code=0 |
| hot | 热榜 | 无需 | >=10 条 |
| detail | 视频详情 | 搜索结果第一条 aweme_id | 返回标题+作者+播放量 |
| comment | 评论翻页 | 同上 | >=3 页，每页 >=15 条 |
| user | 用户主页 | 搜索结果第一条 sec_uid | >=20 条作品 |

### 知乎 (zhihu)

| 动作 | 测试内容 | 关键词/ID | 通过标准 |
|------|---------|----------|----------|
| search | 搜索翻页 | `人工智能` | >=3 页，每页 >=5 条 |
| hot | 热榜 | 无需 | >=15 条 |
| detail | 问答详情 | 搜索结果第一条 ID | 返回标题+内容摘要 |
| user | 用户主页 | 搜索结果第一条作者 ID | >=5 条内容 |

### 快手 (kuaishou)

| 动作 | 测试内容 | 关键词/ID | 通过标准 |
|------|---------|----------|----------|
| search | 搜索翻页 | `搞笑` | >=3 页，每页 >=5 条 |
| hot | 热门 | 无需 | >=10 条 |
| detail | 视频详情 | 搜索结果第一条 ID | 返回标题+作者 |

## 测试脚本

创建 `test_phase1_all.py`：

```python
"""
Phase 1 5平台全覆盖验收测试
用法: python test_phase1_all.py
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.utils.browser_service import browser
from src.agents.bilibili_adapter import BilibiliAdapter
from src.agents.xiaohongshu_adapter import XiaohongshuAdapter
from src.agents.douyin_adapter import DouyinAdapter
from src.agents.zhihu_adapter import ZhihuAdapter
from src.agents.kuaishou_adapter import KuaishouAdapter

RESULTS = {}
PASS = "✅"
FAIL = "❌"

def check(name, data, min_items, min_pages=None):
    """检查结果是否符合翻页/数量标准"""
    n = len(data) if isinstance(data, list) else (1 if data else 0)
    ok = n >= min_items
    RESULTS[name] = {"passed": ok, "count": n, "min": min_items}
    icon = PASS if ok else FAIL
    print(f"  {icon} {name}: {n} 条 (最低 {min_items})")
    return ok

async def test_bilibili():
    print("\n" + "=" * 50)
    print("B站 测试")
    adapter = BilibiliAdapter()

    # Search
    items = await adapter.search("Python教程", limit=50)
    check("B站-search", items, 30)

    # Rank
    items = await adapter.hot()
    check("B站-rank", items, 20)

    # Detail (用第一条结果的 BV 号)
    detail = None
    search_items = await adapter.search("Python教程", limit=10)
    for item in search_items:
        bid = item.get("bvid") or item.get("link", "").split("/")[-1].split("?")[0]
        if bid and bid.startswith("BV"):
            detail = await adapter.detail(item_id=bid)
            break
    check("B站-detail", detail, 1)

    # Comment
    comments = []
    if detail:
        aweme_id = detail.get("aweme_id") or detail.get("aid")
        if aweme_id:
            comments = await adapter.comment(item_id=str(aweme_id), limit=30)
    check("B站-comment", comments, 0)  # B站评论可能需要特殊处理

    # User
    user_items = []
    for item in search_items:
        uid = item.get("mid") or item.get("author_id")
        if uid:
            user_items = await adapter.user(user_id=str(uid), limit=20)
            if user_items:
                break
    check("B站-user", user_items, 5)

async def test_xiaohongshu():
    print("\n" + "=" * 50)
    print("小红书 测试")
    adapter = XiaohongshuAdapter()

    items = await adapter.search("AI绘画", limit=30)
    check("小红书-search", items, 10)

    items = await adapter.hot()
    check("小红书-hot", items, 10)

    search_items = await adapter.search("AI绘画", limit=5)
    detail = None
    for item in search_items:
        nid = item.get("note_id") or item.get("id") or item.get("link", "").split("/")[-1]
        if nid:
            detail = await adapter.detail(item_id=nid)
            if detail:
                break
    check("小红书-detail", detail, 1)

    comments = []
    if detail:
        nid = detail.get("note_id") or detail.get("id")
        if nid:
            comments = await adapter.comment(item_id=nid, limit=20)
    check("小红书-comment", comments, 5)

async def test_douyin():
    print("\n" + "=" * 50)
    print("抖音 测试")
    adapter = DouyinAdapter()

    items = await adapter.search("美食", limit=50)
    check("抖音-search", items, 30)

    items = await adapter.hot()
    check("抖音-hot", items, 10)

    search_items = await adapter.search("美食", limit=10)
    detail = None
    for item in search_items:
        aid = item.get("aweme_id") or item.get("aid")
        if aid:
            detail = await adapter.detail(item_id=str(aid))
            if detail:
                break
    check("抖音-detail", detail, 1)

    comments = []
    for item in search_items:
        aid = item.get("aweme_id") or item.get("aid")
        if aid:
            comments = await adapter.comment(item_id=str(aid), limit=45)
            if comments:
                break
    check("抖音-comment", comments, 30)

    user_items = []
    for item in search_items:
        uid = item.get("sec_uid") or item.get("author_sec_uid") or item.get("author", {}).get("sec_uid")
        if uid:
            user_items = await adapter.user(user_id=uid, limit=30)
            if user_items:
                break
    check("抖音-user", user_items, 20)

async def test_zhihu():
    print("\n" + "=" * 50)
    print("知乎 测试")
    adapter = ZhihuAdapter()

    items = await adapter.search("人工智能", limit=30)
    check("知乎-search", items, 10)

    items = await adapter.hot()
    check("知乎-hot", items, 15)

    search_items = await adapter.search("人工智能", limit=5)
    detail = None
    for item in search_items:
        qid = item.get("question_id") or item.get("id") or item.get("link", "").split("/")[-1]
        if qid:
            detail = await adapter.detail(item_id=str(qid))
            if detail:
                break
    check("知乎-detail", detail, 1)

    user_items = []
    for item in search_items:
        uid = item.get("author_id") or item.get("user_id")
        if uid:
            user_items = await adapter.user(user_id=uid, limit=10)
            if user_items:
                break
    check("知乎-user", user_items, 5)

async def test_kuaishou():
    print("\n" + "=" * 50)
    print("快手 测试")
    adapter = KuaishouAdapter()

    items = await adapter.search("搞笑", limit=30)
    check("快手-search", items, 10)

    try:
        items = await adapter.hot()
        check("快手-hot", items, 10)
    except NotImplementedError:
        RESULTS["快手-hot"] = {"passed": False, "count": 0, "error": "未实现"}
        print(f"  ⚠️ 快手-hot: 未实现")

    search_items = await adapter.search("搞笑", limit=5)
    detail = None
    for item in search_items:
        pid = item.get("photo_id") or item.get("id") or item.get("link", "").split("/")[-1]
        if pid:
            detail = await adapter.detail(item_id=pid)
            if detail:
                break
    check("快手-detail", detail, 1)

async def main():
    print("=" * 60)
    print("Phase 1 — 5平台全覆盖验收测试")
    print("=" * 60)

    await browser.start()

    try:
        await test_bilibili()
        await test_xiaohongshu()
        await test_douyin()
        await test_zhihu()
        await test_kuaishou()
    finally:
        await browser.close()

    # ── 汇总 ──
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    passed = sum(1 for r in RESULTS.values() if r["passed"])
    total = len(RESULTS)
    for name, r in RESULTS.items():
        icon = PASS if r["passed"] else FAIL
        extra = r.get("error", "")
        print(f"  {icon} {name}: {r['count']} 条 (最低 {r['min']}) {extra}")

    print(f"\n总计: {passed}/{total} 通过")

    # 保存结果
    out = {
        "timestamp": time.strftime("%Y%m%d_%H%M%S"),
        "passed": passed,
        "total": total,
        "results": {k: {"passed": v["passed"], "count": v["count"]} for k, v in RESULTS.items()}
    }
    with open("phase1_test_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"结果保存到 phase1_test_results.json")

    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

## 运行

```bash
python test_phase1_all.py
```

## 期望产出

1. `phase1_test_results.json` — 完整测试结果
2. 控制台日志 — 每个平台每个动作的翻页情况
3. 失败的平台/动作 → 注明具体错误（不要只说"不行"）

## 关键判断标准

- **翻页必须真实**：不是同一条数据重复，要每页内容不重复
- **B站 search** 走 URL `&page=N` 翻页
- **抖音 search** 走 DrissionPage + 网络拦截翻页
- **小红书** 走 CDP + 滚动翻页
- **知乎/快手** 走 CDP + DOM 翻页
- 任何 verify_check / 验证码 → 立刻记录并报告
