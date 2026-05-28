"""定时巡检引擎 — 监控关键词，增量发现新内容时回调通知。"""
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from src.utils.checkpoint import get_checkpoint
from src.utils.logger import logger

_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
_WATCH_LOG = _LOG_DIR / "watcher.log"


class KeywordWatcher:
    """定时监控关键词，增量发现新内容。

    用法:
        watcher = KeywordWatcher(["AI", "Python"], platforms=["bilibili", "douyin"])
        await watcher.watch_loop()
    """

    def __init__(
        self,
        keywords: list[str],
        platforms: list[str] | None = None,
        interval_minutes: int = 60,
        limit: int = 20,
        callback: Callable | None = None,
    ):
        self.keywords = keywords
        self.platforms = platforms or ["bilibili"]
        self.interval = max(interval_minutes, 1)
        self.limit = limit
        self.callback = callback
        self._running = False
        self._stats: dict[str, dict] = {}

    async def check_once(self) -> dict[str, list[dict]]:
        """单次巡检：搜索→去重→只保留新内容。返回 {keyword: [new_items]}。"""
        results = {}
        ck = get_checkpoint()

        for kw in self.keywords:
            logger.info(f"[watcher] 巡检: {kw}")
            try:
                from src.orchestrator import run_pipeline
                pipe_result = await run_pipeline(
                    keyword=kw, platforms=self.platforms,
                    limit=self.limit, pipeline_mode="simple",
                )
                items = pipe_result.get("final_output", [])
                new_items = ck.filter_new_items(items, f"watcher_{kw}")
                if new_items:
                    logger.info(f"[watcher] {kw}: 发现 {len(new_items)} 条新内容")
                    self._log_new(kw, new_items)
                    results[kw] = new_items
                    if self.callback:
                        try:
                            await self.callback(kw, new_items)
                        except Exception as e:
                            logger.warning(f"[watcher] 回调失败: {e}")
                else:
                    logger.debug(f"[watcher] {kw}: 无新内容")
                self._stats[kw] = {
                    "last_check": datetime.now().isoformat(),
                    "total_items": len(items),
                    "new_items": len(new_items),
                }
            except Exception as e:
                logger.error(f"[watcher] {kw} 巡检失败: {e}")
                self._stats[kw] = {"last_check": datetime.now().isoformat(), "error": str(e)}

        return results

    async def watch_loop(self):
        """无限循环巡检。"""
        self._running = True
        logger.info(f"[watcher] 启动巡检: {self.keywords}, 间隔 {self.interval}min")
        _LOG_DIR.mkdir(parents=True, exist_ok=True)

        while self._running:
            start = time.time()
            await self.check_once()
            elapsed = time.time() - start
            sleep_sec = max(1, self.interval * 60 - elapsed)
            logger.debug(f"[watcher] 下次巡检: {sleep_sec:.0f}s 后")
            await asyncio.sleep(sleep_sec)

    def stop(self):
        self._running = False

    def status(self) -> dict:
        return {"running": self._running, "keywords": self.keywords, "platforms": self.platforms, "interval_min": self.interval, "stats": self._stats}

    def _log_new(self, keyword: str, items: list[dict]):
        try:
            _LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(_WATCH_LOG, "a", encoding="utf-8") as f:
                for item in items:
                    entry = {
                        "keyword": keyword,
                        "time": datetime.now().isoformat(),
                        "title": item.get("title", ""),
                        "author": item.get("author", ""),
                        "platform": item.get("platform", ""),
                        "link": item.get("link", ""),
                    }
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[watcher] 日志写入失败: {e}")
