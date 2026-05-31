"""LangGraph 节点函数 — 纯 async，无副作用。"""
import asyncio
import hashlib
import json
from typing import Any

import httpx

from src.orchestrator.state import PipelineState
from src.aggregator import _normalize
from src.utils.logger import logger
from config.settings import settings


_search_semaphore = asyncio.Semaphore(getattr(settings, 'MAX_CONCURRENT_SEARCHES', 3))

_ADAPTER_MAP = {
    "bilibili":     ("src.agents.bilibili_adapter",     "BilibiliAdapter"),
    "xiaohongshu":  ("src.agents.xiaohongshu_adapter",  "XiaohongshuAdapter"),
    "douyin":       ("src.agents.douyin_adapter",       "DouyinAdapter"),
    "zhihu":        ("src.agents.zhihu_adapter",        "ZhihuAdapter"),
    "kuaishou":     ("src.agents.kuaishou_adapter",     "KuaishouAdapter"),
    "weibo":        ("src.agents.weibo_adapter",        "WeiboAdapter"),
    "tieba":        ("src.agents.tieba_adapter",        "TiebaAdapter"),
}

_DEFAULT_PLATFORMS = list(_ADAPTER_MAP.keys())

# 🔵 修复: 复用 adapter instance，避免每次新建
_adapter_cache: dict[str, Any] = {}


def _get_adapter(platform: str):
    if platform not in _adapter_cache:
        mod_path, cls_name = _ADAPTER_MAP[platform]
        mod = __import__(mod_path, fromlist=[cls_name])
        _adapter_cache[platform] = getattr(mod, cls_name)()
    return _adapter_cache[platform]


async def _retry(func, max_retries: int = 3, base_delay: float = 2.0):
    """🟡 修复: 纯 async retry，去掉 tenacity 依赖。"""
    last_exc = None
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.debug(f"retry {attempt + 1}/{max_retries}, wait {delay:.1f}s: {exc}")
                await asyncio.sleep(delay)
    raise last_exc


async def search_platform(keyword: str, platform: str, limit: int,
                         sort_type: int = 0, publish_time: int = 0,
                         search_channel: str = "") -> dict:
    """单平台搜索，带 3 次重试 + 指数退避，0结果时 fallback 到 hot。"""
    try:
        adapter = _get_adapter(platform)

        async def _search():
            async with _search_semaphore:
                return await adapter.search(keyword, limit=limit,
                                            sort_type=sort_type, publish_time=publish_time,
                                            search_channel=search_channel)

        items = await _retry(_search)
        logger.info(f"[{platform}] 搜索完成: {len(items)} 条")
        if len(items) < 3:
            logger.info(f"[{platform}] 搜索结果不足 ({len(items)} 条)，尝试热榜 fallback")
            try:
                hot_items = await _retry(lambda: adapter.hot(limit=limit))
                if hot_items and len(hot_items) > len(items):
                    logger.info(f"[{platform}] 热榜 fallback 成功: {len(hot_items)} 条")
                    return hot_items
            except Exception as hot_exc:
                logger.debug(f"[{platform}] 热榜 fallback 也失败: {hot_exc}")
        return items
    except Exception as exc:
        logger.warning(f"[{platform}] 搜索失败 (已重试): {exc}，尝试热榜 fallback")
        try:
            adapter = _get_adapter(platform)
            hot_items = await _retry(lambda: adapter.hot(limit=limit))
            if hot_items:
                logger.info(f"[{platform}] 搜索失败但热榜 fallback 成功: {len(hot_items)} 条")
                return hot_items
        except Exception as hot_exc:
            logger.warning(f"[{platform}] 热榜 fallback 也失败: {hot_exc}")
        return {"error": str(exc)}


def _extract_user_id(item: dict, platform: str) -> str | None:
    """从搜索结果 item 中提取 user_id。各平台字段不同。"""
    # 直接字段
    for key in ("author_id", "user_id", "sec_uid", "mid", "uid", "author_mid"):
        val = item.get(key)
        if val:
            return str(val)
    # 从 author_link / link 提取
    link = item.get("author_link", "") or item.get("link", "") or ""
    patterns = {
        "douyin": r"/user/([A-Za-z0-9_-]+)",
        "xiaohongshu": r"/user/profile/([A-Za-z0-9_-]+)",
        "bilibili": r"/space/(\d+)",
        "zhihu": r"/people/([A-Za-z0-9_-]+)",
        "kuaishou": r"/profile/([A-Za-z0-9_-]+)",
        "weibo": r"/u/(\d+)",
        "tieba": r"un=([A-Za-z0-9_-]+)",
    }
    import re
    pat = patterns.get(platform, "")
    if pat and link:
        m = re.search(pat, link)
        if m:
            return m.group(1)
    return None


async def fetch_account_content(keyword: str, platform: str, limit: int) -> dict:
    """对标账号采集: 搜索账号名 → 提取 user_id → 拉用户主页内容。"""
    search_items = []
    try:
        adapter = _get_adapter(platform)

        # Step 1: 搜索账号名（容错：搜索失败或空结过落热榜）
        try:
            search_items = await adapter.search(keyword, limit=10)
        except Exception as search_exc:
            logger.warning(f"[{platform}] 搜索账号 {keyword} 失败: {search_exc}，尝试热榜")

        if not search_items or not isinstance(search_items, list) or not len(search_items):
            logger.warning(f"[{platform}] 未搜索到账号 {keyword}，尝试热榜")
            try:
                search_items = await adapter.hot(limit=limit)
            except Exception:
                return []

        # Step 2: 过滤作者名匹配 + 提取 user_id
        user_id = None
        for item in search_items:
            if not isinstance(item, dict):
                continue
            author = str(item.get("author", "") or "").strip().lower()
            if author and keyword.lower() in author:
                uid = _extract_user_id(item, platform)
                if uid:
                    user_id = uid
                    break
        if not user_id:
            for item in search_items:
                if isinstance(item, dict):
                    uid = _extract_user_id(item, platform)
                    if uid:
                        user_id = uid
                        break

        if not user_id:
            logger.info(f"[{platform}] 未从搜索结果提取到 user_id，用搜索结果按作者筛选")
            filtered = [it for it in search_items if isinstance(it, dict)
                        and keyword.lower() in str(it.get("author", "") or "").strip().lower()]
            result = filtered[:limit] if filtered else search_items[:limit]
            for it in result:
                if isinstance(it, dict) and not it.get("author"):
                    it["author"] = keyword
            return result

        # Step 3: 用 user 接口拉内容 (单次 + 35s 超时)
        logger.info(f"[{platform}] 找到账号 {keyword}: user_id={user_id}，拉取主页内容")
        user_items = None
        try:
            user_items = await asyncio.wait_for(
                adapter.user(str(user_id), limit=limit),
                timeout=60,
            )
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"[{platform}] user 接口超时/失败: {e}，回落搜索结果")
        if user_items and isinstance(user_items, list) and len(user_items) > 0:
            # 填补空作者（用户主页的视频卡片通常不显示作者名）
            for it in user_items:
                if isinstance(it, dict) and not it.get("author"):
                    it["author"] = keyword
            logger.info(f"[{platform}] 对标账号 {keyword}: {len(user_items)} 条")
            return user_items[:limit]
        else:
            logger.warning(f"[{platform}] user 接口无结果，回退搜索结果")
            # 搜索结果也填补作者
            for it in search_items:
                if isinstance(it, dict) and not it.get("author"):
                    it["author"] = keyword
            return search_items[:limit]

    except Exception as exc:
        logger.warning(f"[{platform}] 对标账号 {keyword} 整体失败: {exc}")
        if search_items:
            filtered = [it for it in search_items if isinstance(it, dict)
                        and keyword.lower() in str(it.get("author", "") or "").strip().lower()]
            result = filtered[:limit] if filtered else search_items[:limit]
            for it in result:
                if isinstance(it, dict) and not it.get("author"):
                    it["author"] = keyword
            return result
        return {"error": str(exc)}


async def account_deep_analyze(state: PipelineState) -> dict[str, Any]:
    """对标账号深度分析：下载代表作 + Agent 分析内容风格。"""
    items = state.get("merged_items", [])
    keyword = state.get("keyword", "")
    platform = state.get("platforms", ["bilibili"])[0] if state.get("platforms") else "bilibili"

    if not items:
        logger.info("account_deep_analyze: 无内容")
        return {}

    # Step 1: 下载 Top5 封面
    paths = []
    try:
        from src.downloader.media_downloader import MediaDownloader
        dl = MediaDownloader(max_concurrent=3)
        dl_results = await dl.download_items(items[:5], topic=keyword, media_type="cover")
        await dl.close()
        paths = [r.filepath for r in dl_results if r.status == "success"]
        logger.info(f"account_deep_analyze: 下载 {len(paths)} 个封面")
    except Exception as e:
        logger.warning(f"account_deep_analyze 下载失败: {e}")

    # Step 2: 跑 TrendScout 分析内容趋势
    trend_reports = {}
    try:
        from src.orchestrator.agents.trend_scout import TrendScout
        scout = TrendScout()
        trend = await scout.run(items=items[:10], platform=platform)
        trend_reports[platform] = trend
    except Exception as e:
        logger.warning(f"account_deep_analyze TrendScout 失败: {e}")

    return {"download_results": paths, "trend_reports": trend_reports}


async def comment_harvest(state: PipelineState) -> dict[str, Any]:
    """评论收割：对搜索结果每个平台取 Top3 视频拉评论（HTTP 优先，浏览器兜底）。"""
    items = state.get("merged_items", [])
    platforms = state.get("platforms", [])

    if not items:
        logger.info("comment_harvest: 无内容")
        return {"harvested_comments": {}}

    all_comments: dict[str, list[dict]] = {}  # platform_id → comments
    for platform in platforms:
        plat_items = [it for it in items if it.get("platform") == platform]
        if not plat_items:
            continue
        try:
            adapter = _get_adapter(platform)
        except Exception:
            continue

        for item in plat_items[:3]:
            item_id = (item.get("bvid") or item.get("aweme_id") or item.get("photo_id")
                       or item.get("note_id") or item.get("weibo_id") or item.get("tid")
                       or item.get("platform_id", ""))
            if not item_id or item_id in all_comments:
                continue
            try:
                comments = await adapter.comment(str(item_id), limit=10)
                for c in (comments if isinstance(comments, list) else []):
                    c["source_title"] = item.get("title", "")
                    c["source_author"] = item.get("author", "")
                if comments:
                    all_comments[item_id] = comments
            except Exception as e:
                logger.debug(f"comment_harvest [{platform}] {item_id}: {e}")

    total = sum(len(v) for v in all_comments.values())
    logger.info(f"comment_harvest: {total} 条评论 ({len(all_comments)} 个内容, {len(platforms)} 平台)")
    return {"harvested_comments": all_comments}


async def merge_results(state: PipelineState) -> dict[str, Any]:
    """聚合归一化 + L1 确定性去重，按 plays/likes 降序。"""
    search_results = state.get("search_results", {})
    all_items = []
    seen_link = set()
    seen_pid = set()
    seen_title_md5 = set()

    for platform, items in search_results.items():
        if isinstance(items, dict) and "error" in items:
            continue
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):  # 🔵 修复: error 检查
                continue
            try:
                normalized = _normalize(item, platform)
            except Exception:
                continue

            link = normalized.get("link", "")
            pid = normalized.get("platform_id", "")
            title = normalized.get("title", "")
            title_hash = hashlib.md5(title.encode()).hexdigest() if title else ""

            if link and link in seen_link:
                continue
            if pid and pid in seen_pid:
                continue
            if title_hash and title_hash in seen_title_md5:
                continue

            if link:
                seen_link.add(link)
            if pid:
                seen_pid.add(pid)
            if title_hash:
                seen_title_md5.add(title_hash)

            all_items.append(normalized)

    def _parse_count(value) -> int:
        """🔵 修复: 不截断，保留完整数值。"""
        s = str(value or 0).replace(",", "").strip()
        if not s:
            return 0
        # 处理 "9.9万" / "1.2亿" 等中文单位
        for unit, multiplier in [("亿", 100000000), ("万", 10000), ("w", 10000), ("k", 1000)]:
            if unit in s.lower():
                try:
                    return int(float(s.lower().replace(unit, "")) * multiplier)
                except ValueError:
                    pass
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return 0

    def _score(item: dict) -> int:
        plays = _parse_count(item.get("plays", 0))
        likes = _parse_count(item.get("likes", 0))
        return plays + likes * 2

    all_items.sort(key=_score, reverse=True)

    logger.info(f"merge_results: {len(all_items)} 条 (去重后)")
    return {"merged_items": all_items}


async def _call_llm(prompt: str, json_mode: bool = False) -> str:
    """统一的 LLM 调用（被批量调用复用）。"""
    api_key = settings.LLM_API_KEY
    api_url = settings.LLM_API_URL
    model = settings.LLM_MODEL

    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 200,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{api_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def llm_filter(state: PipelineState) -> dict[str, Any]:
    """🟡 修复: 批量 LLM 过滤，一次 API 调用处理整批。"""
    if not state.get("llm_filter"):
        return {}

    merged = state.get("merged_items", [])
    if not merged:
        return {"filtered_items": []}

    api_key = settings.LLM_API_KEY
    api_url = settings.LLM_API_URL
    if not api_key or not api_url:
        logger.warning("LLM API 未配置，跳过过滤")
        return {"filtered_items": merged}

    keyword = state["keyword"]

    # 构建批量 prompt
    items_text = "\n".join(
        f"{i}. {item.get('title', '')} | {item.get('author', '')} | {item.get('platform', '')}"
        for i, item in enumerate(merged)
    )
    prompt = (
        f"判断以下内容是否与关键词「{keyword}」相关。"
        f"返回 JSON 数组: [true, false, ...] 对应每条内容。\n{items_text}"
    )

    try:
        result = await _call_llm(prompt, json_mode=True)
        relevance = json.loads(result)
        if isinstance(relevance, list) and len(relevance) == len(merged):
            filtered = [item for item, rel in zip(merged, relevance) if rel]
        else:
            filtered = merged
    except Exception as exc:
        logger.warning(f"LLM filter 失败 (保留原条目): {exc}")
        filtered = merged

    logger.info(f"llm_filter: {len(merged)} -> {len(filtered)} 条")
    return {"filtered_items": filtered}


async def llm_score(state: PipelineState) -> dict[str, Any]:
    """🟡 修复: 批量 LLM 打分，一次 API 调用处理整批。"""
    if not state.get("llm_filter"):
        return {}

    items = state.get("filtered_items", state.get("merged_items", []))
    if not items:
        return {"scored_items": []}

    api_key = settings.LLM_API_KEY
    api_url = settings.LLM_API_URL
    if not api_key or not api_url:
        items_with_default_score = [{**item, "score": 5} for item in items]
        items_with_default_score.sort(key=lambda x: x["score"], reverse=True)
        return {"scored_items": items_with_default_score}

    keyword = state["keyword"]

    items_text = "\n".join(
        f"{i}. {item.get('title', '')} | 播放:{item.get('plays', '0')} | 点赞:{item.get('likes', '0')}"
        for i, item in enumerate(items)
    )
    prompt = (
        f"对以下内容与关键词「{keyword}」的匹配质量打分 (1-10)。"
        f"返回 JSON 数组: [分数1, 分数2, ...]。\n{items_text}"
    )

    try:
        result = await _call_llm(prompt, json_mode=True)
        scores = json.loads(result)
        if isinstance(scores, list) and len(scores) == len(items):
            scored = [{**item, "score": int(s)} for item, s in zip(items, scores)]
        else:
            scored = [{**item, "score": 5} for item in items]
    except Exception as exc:
        logger.warning(f"LLM score 失败 (使用默认分): {exc}")
        scored = [{**item, "score": 5} for item in items]

    scored.sort(key=lambda x: x.get("score", 0), reverse=True)
    logger.info(f"llm_score: {len(scored)} 条已排序")
    return {"scored_items": scored}


async def download_selected(state: PipelineState) -> dict[str, Any]:
    """下载选中视频的封面/视频到本地。"""
    items = state.get("merged_items", [])
    if not items:
        logger.info("download_selected: 无内容可下载")
        return {"download_results": []}

    limit = state.get("limit", 10)
    keyword = state.get("keyword", "general")
    target = items[:limit]

    from src.downloader.media_downloader import MediaDownloader
    dl = MediaDownloader(max_concurrent=3)
    try:
        results = await dl.download_items(target, topic=keyword, media_type="all")
        paths = [r.filepath for r in results if r.status == "success"]
        skipped = sum(1 for r in results if r.status == "skipped")
        failed = sum(1 for r in results if r.status == "failed")
        logger.info(f"download_selected: {len(paths)} 成功, {skipped} 跳过, {failed} 失败")
        return {"download_results": paths}
    finally:
        await dl.close()


async def format_output(state: PipelineState) -> dict[str, Any]:
    """选择最终输出字段。full 模式附加 Agent 报告。"""
    source = (
        state.get("scored_items")
        or state.get("filtered_items")
        or state.get("merged_items", [])
    )
    final = []
    for item in source:
        out = {
            "platform":    item.get("platform", ""),
            "platform_id": item.get("platform_id", ""),
            "title":       item.get("title", ""),
            "author":      item.get("author", ""),
            "plays":       item.get("plays", ""),
            "likes":       item.get("likes", ""),
            "link":        item.get("link", ""),
            "cover_url":   item.get("cover_url", ""),
        }
        if "score" in item:
            out["score"] = item["score"]
        if state.get("include_raw"):
            out["raw"] = {k: v for k, v in item.items() if k not in out}
        final.append(out)

    result: dict[str, Any] = {"final_output": final}

    if state.get("pipeline_mode") == "full":
        for key in (
            "trend_reports", "product_report", "video_report",
            "sentiment_report", "copy_report", "remix_report", "visual_report",
        ):
            val = state.get(key)
            if val:
                result[key] = val

    logger.info(f"format_output: {len(final)} 条")
    return result