"""LangGraph 节点函数 — 纯 async，无副作用。"""
import asyncio
import hashlib
import json
from typing import Any

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.orchestrator.state import PipelineState
from src.aggregator import _FIELD_MAP, _normalize
from src.utils.logger import logger
from config.settings import settings


_ADAPTER_MAP = {
    "bilibili":     ("src.agents.bilibili_adapter",     "BilibiliAdapter"),
    "xiaohongshu":  ("src.agents.xiaohongshu_adapter",  "XiaohongshuAdapter"),
    "douyin":       ("src.agents.douyin_adapter",       "DouyinAdapter"),
    "zhihu":        ("src.agents.zhihu_adapter",        "ZhihuAdapter"),
    "kuaishou":     ("src.agents.kuaishou_adapter",     "KuaishouAdapter"),
}

_DEFAULT_PLATFORMS = list(_ADAPTER_MAP.keys())

_RETRY = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((Exception,)),
    reraise=False,
)


async def search_platform(keyword: str, platform: str, limit: int) -> dict:
    """单平台搜索，带 3 次重试 + 指数退避，失败降级返回 error。"""
    mod_path, cls_name = _ADAPTER_MAP[platform]
    try:
        mod = __import__(mod_path, fromlist=[cls_name])
        adapter_cls = getattr(mod, cls_name)
        adapter = adapter_cls()

        @_RETRY
        async def _search():
            return await adapter.search(keyword, limit=limit)

        items = await _search()
        logger.info(f"[{platform}] 搜索完成: {len(items)} 条")
        return items
    except Exception as exc:
        logger.warning(f"[{platform}] 搜索失败 (已重试): {exc}")
        return {"error": str(exc)}


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
            normalized = _normalize(item, platform)

            # L1 去重
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

    # 按 popularity 降序
    def _parse_count(value) -> int:
        s = str(value or 0).replace(",", "").strip()
        if "万" in s:
            return int(float(s.replace("万", "")) * 10000)
        if "亿" in s:
            return int(float(s.replace("亿", "")) * 100000000)
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


async def llm_filter(state: PipelineState) -> dict[str, Any]:
    """LLM 相关性过滤 — 仅 llm_filter=True 时执行。"""
    if not state.get("llm_filter"):
        return {}

    merged = state.get("merged_items", [])
    if not merged:
        return {"filtered_items": []}

    keyword = state["keyword"]
    api_key = settings.LLM_API_KEY
    api_url = settings.LLM_API_URL
    model = settings.LLM_MODEL

    if not api_key or not api_url:
        logger.warning("LLM API 未配置，跳过过滤")
        return {"filtered_items": merged}

    filtered = []
    for item in merged:
        title = item.get("title", "")
        prompt = (
            f"判断以下内容是否与关键词「{keyword}」相关。\n"
            f"标题: {title}\n"
            f"作者: {item.get('author', '')}\n"
            f'返回 JSON: {{"relevant": true/false, "reason": "一句话理由"}}'
        )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{api_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0,
                        "max_tokens": 100,
                    },
                )
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                if parsed.get("relevant", True):
                    filtered.append(item)
        except Exception as exc:
            logger.warning(f"LLM filter 失败 (保留原条目): {exc}")
            filtered.append(item)

    logger.info(f"llm_filter: {len(merged)} → {len(filtered)} 条")
    return {"filtered_items": filtered}


async def llm_score(state: PipelineState) -> dict[str, Any]:
    """LLM 打分排序 — 仅 llm_filter=True 时执行。"""
    if not state.get("llm_filter"):
        return {}

    items = state.get("filtered_items", state.get("merged_items", []))
    if not items:
        return {"scored_items": []}

    keyword = state["keyword"]
    api_key = settings.LLM_API_KEY
    api_url = settings.LLM_API_URL
    model = settings.LLM_MODEL

    if not api_key or not api_url:
        items_with_default_score = [{"score": 5, **item} for item in items]
        items_with_default_score.sort(key=lambda x: x["score"], reverse=True)
        return {"scored_items": items_with_default_score}

    scored = []
    for item in items:
        title = item.get("title", "")
        prompt = (
            f"对以下内容与关键词「{keyword}」的匹配质量打分 (1-10):\n"
            f"标题: {title}\n"
            f"播放量: {item.get('plays', '0')}\n"
            f"点赞: {item.get('likes', '0')}\n"
            f'返回 JSON: {{"score": 1-10, "reason": "一句话理由"}}'
        )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{api_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0,
                        "max_tokens": 100,
                    },
                )
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                score = int(parsed.get("score", 5))
                scored.append({**item, "score": score, "score_reason": parsed.get("reason", "")})
        except Exception as exc:
            logger.warning(f"LLM score 失败 (使用默认分): {exc}")
            scored.append({**item, "score": 5})

    scored.sort(key=lambda x: x.get("score", 0), reverse=True)
    logger.info(f"llm_score: {len(scored)} 条已排序")
    return {"scored_items": scored}


async def format_output(state: PipelineState) -> dict[str, Any]:
    """选择最终输出字段，移除 raw。"""
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
        }
        if "score" in item:
            out["score"] = item["score"]
            out["score_reason"] = item.get("score_reason", "")
        final.append(out)

    logger.info(f"format_output: {len(final)} 条")
    return {"final_output": final}
