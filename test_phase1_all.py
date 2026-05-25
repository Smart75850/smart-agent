"""
Phase 1 5平台全覆盖验收测试
用法: python test_phase1_all.py
"""
import asyncio
import json
import re
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
PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"


def check(name, data, min_items, min_pages=None):
    n = len(data) if isinstance(data, list) else (1 if data else 0)
    ok = n >= min_items
    RESULTS[name] = {"passed": ok, "count": n, "min": min_items}
    icon = PASS if ok else FAIL
    print(f"  {icon} {name}: {n} 条 (最低 {min_items})")
    return ok


def extract_bvid(link):
    m = re.search(r"BV[a-zA-Z0-9]+", link or "")
    return m.group(0) if m else ""


def extract_question_id(link):
    m = re.search(r"/question/(\d+)", link or "")
    return m.group(1) if m else ""


def extract_photo_id(link):
    m = re.search(r"/photo/(\w+)", link or "")
    return m.group(1) if m else ""


def extract_user_id(url):
    m = re.search(r"/people/([\w-]+)", url or "")
    return m.group(1) if m else ""


async def test_bilibili():
    print("\n" + "=" * 50)
    print("B站 测试")
    adapter = BilibiliAdapter()

    items = await adapter.search("Python教程", limit=50)
    check("B站-search", items, 30)

    items = await adapter.hot()
    check("B站-rank", items, 20)

    search_items = await adapter.search("Python教程", limit=10)
    detail = None
    for item in search_items:
        bid = item.get("bvid") or extract_bvid(item.get("link", ""))
        if bid:
            detail = await adapter.detail(item_id=bid)
            break
    check("B站-detail", detail, 1)

    comments = []
    for item in search_items:
        bid = item.get("bvid") or extract_bvid(item.get("link", ""))
        if bid:
            comments = await adapter.comment(item_id=bid, limit=30)
            if comments:
                break
    check("B站-comment", comments, 10)

    user_items = []
    for item in search_items:
        uid = item.get("mid") or item.get("author_id")
        if not uid and detail:
            uid = detail.get("mid")
        if uid:
            user_items = await adapter.user(user_id=str(uid), limit=20)
            if len(user_items) >= 5:
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
        nid = item.get("note_id") or item.get("id")
        if not nid:
            link = item.get("link", "")
            m = re.search(r"/explore/(\w+)", link)
            nid = m.group(1) if m else ""
        if nid:
            detail = await adapter.detail(item_id=nid)
            if detail and detail.get("title"):
                break
    check("小红书-detail", detail, 1)

    comments = []
    for item in search_items:
        nid = item.get("note_id") or item.get("id")
        if not nid:
            link = item.get("link", "")
            m = re.search(r"/explore/(\w+)", link)
            nid = m.group(1) if m else ""
        if nid:
            comments = await adapter.comment(item_id=nid, limit=20)
            if comments:
                break
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
    check("抖音-comment", comments, 15)

    user_items = []
    for item in search_items:
        uid = item.get("sec_uid") or item.get("author_sec_uid") or (item.get("author") or {}).get("sec_uid")
        if uid:
            user_items = await adapter.user(user_id=uid, limit=30)
            if len(user_items) >= 10:
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
        qid = item.get("question_id") or item.get("id") or extract_question_id(item.get("link", ""))
        if qid:
            detail = await adapter.detail(item_id=str(qid))
            if detail:
                break
    check("知乎-detail", detail, 1)

    user_items = []
    # 从 detail 的 top_answers 中提取用户 ID
    if detail:
        for ans in (detail.get("top_answers") or []):
            author_url = ans.get("author_url", "")
            uid = extract_user_id(author_url)
            if uid:
                user_items = await adapter.user(user_id=uid, limit=10)
                if len(user_items) >= 3:
                    break
    # 兜底：从搜索结果中查找
    if not user_items:
        for item in search_items:
            uid = item.get("author_id") or item.get("user_id") or item.get("author", {}).get("id")
            if uid:
                user_items = await adapter.user(user_id=uid, limit=10)
                if len(user_items) >= 3:
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
        RESULTS["快手-hot"] = {"passed": False, "count": 0, "min": 10, "error": "未实现"}
        print(f"  {WARN} 快手-hot: 未实现，跳过")

    search_items = await adapter.search("搞笑", limit=5)
    detail = None
    for item in search_items:
        pid = item.get("photo_id") or item.get("id") or extract_photo_id(item.get("link", ""))
        if pid:
            detail = await adapter.detail(item_id=pid)
            if detail:
                break
    check("快手-detail", detail, 1)


async def main():
    print("=" * 60)
    print("Phase 1 — 5平台全覆盖验收测试 (CDP模式)")
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

    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    passed = sum(1 for r in RESULTS.values() if r.get("passed"))
    total = len(RESULTS)
    for name, r in RESULTS.items():
        icon = PASS if r.get("passed") else (WARN if r.get("error") else FAIL)
        extra = r.get("error", "")
        print(f"  {icon} {name}: {r['count']} 条 (最低 {r['min']}) {extra}")

    print(f"\n总计: {passed}/{total} 通过")

    out = {
        "timestamp": time.strftime("%Y%m%d_%H%M%S"),
        "passed": passed,
        "total": total,
        "results": {k: {"passed": v.get("passed"), "count": v["count"]} for k, v in RESULTS.items()},
    }
    with open("phase1_test_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"结果保存到 phase1_test_results.json")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
