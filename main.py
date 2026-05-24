#!/usr/bin/env python3
"""Smart Agent CLI 入口點。"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from src.utils.browser_service import browser
from src.utils.logger import logger
from store import get_store
from config.settings import settings

# ── adapter imports ──────────────────────────────────────────────
# raw function 保留俾 MCP Server 用，main.py 用 Adapter 統一接口
from src.agents.bilibili_adapter import BilibiliAdapter
from src.agents.xiaohongshu_adapter import XiaohongshuAdapter
from src.agents.douyin_adapter import DouyinAdapter
from src.agents.zhihu_adapter import ZhihuAdapter
from src.agents.kuaishou_adapter import KuaishouAdapter

_ADAPTERS = {
    "bilibili": BilibiliAdapter(),
    "xiaohongshu": XiaohongshuAdapter(),
    "douyin": DouyinAdapter(),
    "zhihu": ZhihuAdapter(),
    "kuaishou": KuaishouAdapter(),
}

# all 模式：跑晒所有平台指定 type
_ALL_SEARCH  = ["bilibili", "xiaohongshu", "douyin", "zhihu", "kuaishou"]
_ALL_HOT     = ["bilibili", "xiaohongshu", "douyin", "zhihu", "kuaishou"]
_ALL_DETAIL  = ["bilibili", "xiaohongshu", "douyin", "zhihu", "kuaishou"]
_ALL_COMMENT = ["bilibili", "xiaohongshu", "douyin", "zhihu", "kuaishou"]
_ALL_USER    = ["bilibili", "xiaohongshu", "douyin", "zhihu", "kuaishou"]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Smart Agent — 多平台內容採集工具"
    )
    parser.add_argument(
        "--platform", default="bilibili",
        choices=["bilibili", "xiaohongshu", "douyin", "zhihu", "kuaishou", "all"],
        help="目標平台（預設 bilibili）",
    )
    parser.add_argument(
        "--keyword", default="",
        help="搜索關鍵詞（預設空，rank/hot 唔需要）",
    )
    parser.add_argument(
        "--type", default="search",
        choices=["search", "hot", "rank", "detail", "comment", "user"],
        help="操作類型（預設 search，按平台決定可用選項）",
    )
    parser.add_argument(
        "--engine", default="playwright", choices=["playwright", "cdp"],
        help="瀏覽器引擎（預設 playwright）",
    )
    parser.add_argument(
        "--output", default="./output",
        help="輸出目錄（預設 ./output）",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="結果數量上限（optional）",
    )
    return parser.parse_args(argv)


def _build_kwargs(args, method):
    """根據 adapter method 名構造 kwargs dict。"""
    if method == "search":
        return {"keyword": args.keyword} if args.keyword else {}
    if method in ("detail", "comment"):
        return {"item_id": args.keyword}
    if method == "user":
        return {"user_id": args.keyword}
    # hot / rank 無需 keyword
    return {}


def build_tasks(args):
    """根據 CLI args 生成 (platform_name, type, callable, kwargs) 列表。"""
    tasks = []

    if args.platform == "all":
        if args.type == "search":
            platforms = _ALL_SEARCH
        elif args.type in ("hot", "rank"):
            platforms = _ALL_HOT
        elif args.type == "detail":
            platforms = _ALL_DETAIL
        elif args.type == "comment":
            platforms = _ALL_COMMENT
        elif args.type == "user":
            platforms = _ALL_USER
        else:
            platforms = _ALL_SEARCH
    else:
        platforms = [args.platform]

    for platform in platforms:
        t = args.type
        if t == "rank" and platform != "bilibili":
            t = "hot"

        if t == "user" and platform == "douyin":
            # 兼容舊 raw function（user 已納入 adapter 接口）
            from src.agents.douyin_adapter import douyin_user_videos
            tasks.append((platform, t, douyin_user_videos, {"user_id": args.keyword}))
            continue

        adapter = _ADAPTERS.get(platform)
        if adapter is None:
            continue

        method_map = {
            "search": (adapter.search, True),
            "hot":    (adapter.hot, True),
            "rank":   (adapter.hot, True),
            "detail": (adapter.detail, True),
            "comment": (adapter.comment, True),
            "user":   (adapter.user, True),
        }
        entry = method_map.get(t)
        if entry is None:
            continue
        func, is_adapter = entry
        kwargs = _build_kwargs(args, t)
        tasks.append((platform, t, func, kwargs))

    return tasks


def limit_results(data, n):
    """對結果 list 或 dict 做上限截斷。"""
    if n is None:
        return data
    if isinstance(data, list):
        return data[:n]
    return data


async def main():
    args = parse_args()

    # ── engine ───────────────────────────────────────────────
    os.environ["BROWSER_ENGINE"] = args.engine

    # ── output dir ───────────────────────────────────────────
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── build 執行計劃 ──────────────────────────────────────
    tasks = build_tasks(args)
    if not tasks:
        logger.error(f"platform={args.platform} 唔支援 type={args.type}")
        sys.exit(1)

    # ── 啟動 browser ────────────────────────────────────────
    # 全部 tasks 共享一個 browser 實例
    await browser.start()

    all_results = {}
    ts = time.strftime("%Y%m%d_%H%M%S")

    try:
        for platform, action, func, kwargs in tasks:
            key = f"{platform}_{action}"
            try:
                result = await func(**kwargs)
                # adapter 方法返回 list[dict]/dict，raw function 返回 JSON str
                if isinstance(result, str):
                    data = json.loads(result)
                else:
                    data = result
                if args.limit is not None:
                    data = limit_results(data, args.limit)
                all_results[key] = data
                # store 儲存（per-platform）
                store = get_store(settings.STORE_BACKEND)
                filepath = store.save(data, args.output, key)
                # stdout 輸出
                count = len(data) if isinstance(data, list) else 1
                logger.info(f"[{platform}] {action}: {count} 條")
                logger.info(f"  → Saved to {filepath}")
            except Exception as exc:
                err_msg = f"{type(exc).__name__}: {exc}"
                all_results[key] = {"error": err_msg}
                logger.error(f"[{platform}] {action}: ERROR — {err_msg}")

        # ── 寫 output ───────────────────────────────────────
        out_path = out_dir / f"result_{ts}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        print(f"\n結果已保存: {out_path}")

    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
