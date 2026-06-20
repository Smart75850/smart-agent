#!/usr/bin/env python3
"""Smart Agent CLI 入口點。"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Windows 控制台 UTF-8 编码修复
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.utils.browser_service import browser
from src.utils.logger import logger
from src.utils.checkpoint import get_checkpoint
from store import get_store, save_with_dedup
from config.settings import settings

# ── adapter imports ──────────────────────────────────────────────
# raw function 保留俾 MCP Server 用，main.py 用 Adapter 統一接口
from src.agents.bilibili_adapter import BilibiliAdapter
from src.agents.xiaohongshu_adapter import XiaohongshuAdapter
from src.agents.douyin_adapter import DouyinAdapter
from src.agents.zhihu_adapter import ZhihuAdapter
from src.agents.kuaishou_adapter import KuaishouAdapter
from src.agents.weibo_adapter import WeiboAdapter
from src.agents.tieba_adapter import TiebaAdapter

_ADAPTERS = {
    "bilibili": BilibiliAdapter(),
    "xiaohongshu": XiaohongshuAdapter(),
    "douyin": DouyinAdapter(),
    "zhihu": ZhihuAdapter(),
    "kuaishou": KuaishouAdapter(),
    "weibo": WeiboAdapter(),
    "tieba": TiebaAdapter(),
}

# all 模式：跑晒所有平台指定 type
_ALL_PLATFORMS = ["bilibili", "xiaohongshu", "douyin", "zhihu", "kuaishou", "weibo", "tieba"]
_ALL_SEARCH  = _ALL_PLATFORMS
_ALL_HOT     = _ALL_PLATFORMS
_ALL_DETAIL  = _ALL_PLATFORMS
_ALL_COMMENT = _ALL_PLATFORMS
_ALL_USER    = _ALL_PLATFORMS


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Smart Agent — 多平台內容採集工具"
    )
    parser.add_argument(
        "--platform", default="bilibili",
        choices=["bilibili", "xiaohongshu", "douyin", "zhihu", "kuaishou", "weibo", "tieba", "all"],
        help="目標平台（預設 bilibili）",
    )
    parser.add_argument(
        "--keyword", default="",
        help="搜索關鍵詞（預設空，rank/hot 唔需要）",
    )
    parser.add_argument(
        "--type", default="search",
        choices=["search", "hot", "rank", "detail", "comment", "user", "aggregate", "trend", "clone"],
        help="操作類型（預設 search，按平台決定可用選項）",
    )
    parser.add_argument(
        "--engine", default="playwright", choices=["playwright", "cdp", "camoufox"],
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
    parser.add_argument(
        "--resume", action="store_true",
        help="斷點續跑：跳過已完成任務",
    )
    parser.add_argument(
        "--llm-filter", action="store_true",
        help="啟用 LLM 過濾打分（僅 --engine=langgraph 時有效）",
    )
    parser.add_argument(
        "--pipeline", default="simple", choices=["simple", "full", "download", "sentiment"],
        help="管道模式: simple=搜索合并, full=完整Agent分析链+下载, download=搜索+下载, sentiment=舆情采集 (仅 --type=aggregate 时有效)",
    )
    parser.add_argument(
        "--download", action="store_true",
        help="搜索后自动下载视频/封面 (仅 --type=search 时有效)",
    )
    parser.add_argument(
        "--url", default="",
        help="视频链接（--type=clone 时需要）",
    )
    parser.add_argument(
        "--max-frames", type=int, default=30,
        help="视频抽帧上限（--type=clone 时有效，预设30）",
    )
    parser.add_argument(
        "--stream", action="store_true",
        help="啟用 SSE 流式輸出（僅 --engine=langgraph 時有效）",
    )
    parser.add_argument(
        "--list-platforms", action="store_true",
        help="列出支援平台",
    )
    parser.add_argument(
        "--cookie-bridge", action="store_true",
        help="啟動 CookieBridge 本地服務，接收 Chrome Extension 同步的 cookies",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="只顯示執行計劃，唔實際執行",
    )
    parser.add_argument(
        "--schedule", type=str, default=None,
        help="定時執行 (cron 表達式)",
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



async def _run_scheduled(schedule: str, func, *args, **kwargs):
    """定時執行封裝。支援 cron 表達式。"""
    import time
    from datetime import datetime
    try:
        from croniter import croniter
        cron = croniter(schedule, datetime.now())
        next_run = cron.get_next(datetime)
        wait = (next_run - datetime.now()).total_seconds()
        logger.info(f"定時任務: next run at {next_run}")
        await asyncio.sleep(max(0, wait))
    except ImportError:
        # 無 croniter 時用簡單 interval (支援 "every-Nh" 格式)
        if schedule.startswith("every-"):
            parts = schedule.replace("every-", "").split("h")
            hours = float(parts[0]) if parts else 1
            logger.info(f"定時任務: every {hours}h")
            await asyncio.sleep(hours * 3600)
        else:
            logger.error("需要安裝 croniter: pip install croniter")
            return
    await func(*args, **kwargs)


async def _aggregate_wrapper(args):
    """aggregate 定時包裝。"""
    from src.orchestrator import run_pipeline
    platforms = None if args.platform == "all" else [args.platform]
    result = await run_pipeline(
        keyword=args.keyword or "",
        limit=args.limit or 30,
        llm_filter=args.llm_filter,
        pipeline_mode=args.pipeline,
        platforms=platforms,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

async def main():
    args = parse_args()

    # ── list-platforms ────────────────────────────────────
    if args.list_platforms:
        platforms = ["bilibili", "xiaohongshu", "douyin", "zhihu", "kuaishou", "weibo", "tieba"]
        print("支援平台:")
        for p in platforms:
            print(f"  {p}")
        return

    if args.cookie_bridge:
        from src.cookie_bridge.server import start_server
        start_server()
        return

    # ── dry-run ──────────────────────────────────────────
    if args.dry_run:
        tasks = build_tasks(args)
        print(f"執行計劃 ({len(tasks)} 個任務):")
        for plat, action, _, _ in tasks:
            print(f"  [{plat}] {action}")
        return

    # ── trend scout ────────────────────────────────────────
    if args.type == "trend":
        from src.orchestrator.agents import TrendScout
        from dataclasses import asdict
        scout = TrendScout()
        platforms = _ALL_HOT if args.platform == "all" else [args.platform]
        trend_dir = Path(args.output)
        trend_dir.mkdir(parents=True, exist_ok=True)
        trend_ts = time.strftime("%Y%m%d_%H%M%S")
        await browser.start()
        try:
            for p in platforms:
                report = await scout.run(platform=p, keyword=args.keyword, limit=args.limit or 20)
                out_path = trend_dir / f"trend_{p}_{trend_ts}.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(asdict(report), f, ensure_ascii=False, indent=2)
                print(f"\n[{p}] {report.summary}")
                for item in report.items[:5]:
                    print(f"  viral={item.viral_score:3d} | {item.title[:40]}")
                print(f"  ...共 {report.total_candidates} 個候選 → {out_path}")
        finally:
            await browser.close()
        return

    # ── aggregate 快速路徑 ───────────────────────────────────
    if args.type == "aggregate":
        # 检查 API Key 配置
        has_llm = bool(settings.DEEPSEEK_API_KEY or settings.LLM_API_KEY)
        if not has_llm and args.pipeline in ("full", "sentiment"):
            print("=" * 60)
            print("  ⚠️  未配置 LLM，AI 分析将降级为模板模式")
            print()
            print("  推荐方案一：本地 Ollama（免费，无需联网，中文最佳）")
            print("    1. 下载 Ollama: https://ollama.com")
            print("    2. 拉取模型: ollama pull qwen3:14b")
            print("    3. 在项目 .env 中添加：")
            print("       LLM_API_URL=http://localhost:11434/v1")
            print("       LLM_MODEL=qwen3:14b")
            print()
            print("  推荐方案二：DeepSeek 云端（¥10 起充，效果更强）")
            print("    注册 https://platform.deepseek.com → 获取 Key")
            print("    在 .env 中添加: DEEPSEEK_API_KEY=sk-你的key")
            print()
            print("  无 LLM 时搜索/采集功能不受影响，仅 AI 分析降级")
            print("=" * 60)
            print()

        platforms = None if args.platform == "all" else [args.platform]
        if args.stream:
            from src.orchestrator import run_pipeline_stream
            async for event in run_pipeline_stream(
                keyword=args.keyword or "",
                limit=args.limit or 30,
                llm_filter=args.llm_filter,
                pipeline_mode=args.pipeline,
                platforms=platforms,
            ):
                print(json.dumps(event, ensure_ascii=False))
        else:
            from src.orchestrator import run_pipeline
            result = await run_pipeline(
                keyword=args.keyword or "",
                limit=args.limit or 30,
                llm_filter=args.llm_filter,
                pipeline_mode=args.pipeline,
                platforms=platforms,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return


    # ── clone: 视频克隆分析 ────────────────────────────────
    if args.type == "clone":
        if not args.url:
            logger.error("--type clone 需要 --url 参数（视频链接）")
            sys.exit(1)
        from src.orchestrator.agents.video_cloner import VideoCloneAgent
        from dataclasses import asdict
        agent = VideoCloneAgent()
        logger.info(f"开始分析视频: {args.url}")
        from src.orchestrator.agents.video_cloner import detect_platform
        plat = args.platform if args.platform not in ("all", "bilibili") else ""
        if not plat:
            plat = detect_platform(args.url)
        logger.info(f"平台: {plat or '自动检测失败'}")
        report = await agent.run(
            video_url=args.url,
            platform=plat,
            max_frames=args.max_frames,
        )
        # 输出操作清单（可直接跟住做）
        from src.orchestrator.agents.video_cloner import format_checklist
        print(format_checklist(report))
        if args.output:
            out_path = Path(args.output)
            out_path.write_text(format_checklist(report), encoding="utf-8")
            logger.info(f"清单已保存: {out_path}")
        return

    # ── schedule ──────────────────────────────────────────
    if args.schedule:
        logger.info(f"啟動定時模式: {args.schedule}")
        await _run_scheduled(args.schedule, _aggregate_wrapper, args)
        return

    # ── engine ───────────────────────────────────────────────
    # 用户已设环境变量时优先使用，否则用命令行参数（默认 playwright）
    if "BROWSER_ENGINE" not in os.environ:
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
    ck = get_checkpoint()

    # ── resume 模式：跳過已完成任務 ──────────────────────────
    if args.resume:
        before = len(tasks)
        tasks = [
            t for t in tasks
            if not ck.is_task_done(t[0], t[1], args.keyword)
        ]
        skipped = before - len(tasks)
        if skipped:
            logger.info(f"--resume 模式：跳過 {skipped} 個已完成任務")

    try:
        task_idx = 0
        task_total = len(tasks)

        for platform, action, func, kwargs in tasks:
            key = f"{platform}_{action}"
            # 寫入 checkpoint（pending→running）
            ck.save_task(platform, action, args.keyword, status="running")

            task_idx += 1
            logger.info(f"[{task_idx}/{task_total}] {platform} {action}: {args.keyword or 'hot'}")

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
                filepath = save_with_dedup(store, data, args.output, key)
                # stdout 輸出
                count = len(data) if isinstance(data, list) else 1
                logger.info(f"[{platform}] {action}: {count} 條")
                logger.info(f"  → Saved to {filepath}")
                ck.mark_done(platform, action, args.keyword, collected_count=count)
            except Exception as exc:
                err_msg = f"{type(exc).__name__}: {exc}"
                all_results[key] = {"error": err_msg}
                logger.error(f"[{platform}] {action}: ERROR — {err_msg}")
                ck.mark_failed(platform, action, args.keyword, error_msg=err_msg)

        # ── download ──────────────────────────────────────────
        if args.download and all_results:
            from src.downloader.media_downloader import MediaDownloader
            dl = MediaDownloader()
            all_items = []
            for key, data in all_results.items():
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            if "platform" not in item:
                                item["platform"] = key.split("_")[0]
                            all_items.append(item)
            if all_items:
                dl_results = await dl.download_items(all_items, topic=args.keyword or "general")
                await dl.close()
                paths = [r.filepath for r in dl_results if r.status == "success"]
                logger.info(f"下载完成: {len(paths)}/{len(dl_results)} 个文件")

        # ── final stats ──────────────────────────────────────
        tasks_summary = ck.get_all_tasks()
        done_count = sum(1 for t in tasks_summary if t["status"] == "done")
        failed_count = sum(1 for t in tasks_summary if t["status"] == "failed")
        total = len(tasks_summary)
        logger.info(f"checkpoint 彙總：共 {total} 任務，{done_count} 成功，{failed_count} 失敗")

        # ── 寫 output ───────────────────────────────────────
        out_path = out_dir / f"result_{ts}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        print(f"\n結果已保存: {out_path}")

    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
