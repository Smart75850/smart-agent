"""Media Downloader — 批量下载封面图和视频。

用法:
    dl = MediaDownloader()
    results = await dl.download_items(items, topic="AI绘画", media_type="all")
"""

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx

from config.settings import settings
from src.utils.logger import logger

_SAFE_RE = re.compile(r'[\\/:*?"<>|]')


def _safe_name(s: str, max_len: int = 60) -> str:
    return _SAFE_RE.sub("_", s)[:max_len]


def _ext_from_url(url: str, default: str = ".jpg") -> str:
    path = urlparse(url).path
    ext = Path(path).suffix.lower()
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".bmp"):
        return ext
    if ext in (".mp4", ".mov", ".webm", ".flv", ".m3u8", ".ts"):
        return ext
    return default


@dataclass
class DownloadResult:
    item_id: str = ""
    platform: str = ""
    media_type: str = ""
    url: str = ""
    filepath: str = ""
    size_bytes: int = 0
    status: str = ""           # success / skipped / failed
    error: str = ""


class MediaExtractor:
    """使用浏览器从详情页提取媒体 URL。"""

    def __init__(self):
        self._browser = None  # lazy init via browser_service

    @property
    def browser(self):
        if self._browser is None:
            from src.utils.browser_service import browser as b
            self._browser = b
        return self._browser

    async def extract_cover(self, platform: str, item: dict) -> str:
        handler = getattr(self, f"_cover_{platform}", None)
        if handler:
            return await handler(item)
        return ""

    async def extract_video(self, platform: str, item: dict) -> str:
        handler = getattr(self, f"_video_{platform}", None)
        if handler:
            return await handler(item)
        return ""

    # ── douyin ────────────────────────────────────────────

    async def _cover_douyin(self, item: dict) -> str:
        return item.get("cover_url", "")

    async def _video_douyin(self, item: dict) -> str:
        link = item.get("link", "") or f"https://www.douyin.com/video/{item.get('aweme_id', '')}"
        if not link:
            return ""
        video_urls: list[tuple[str, int]] = []  # (url, content_length)

        async def on_response(resp):
            url = resp.url
            ct = resp.headers.get("content-type", "")
            try:
                cl = int(resp.headers.get("content-length", "0"))
            except Exception:
                cl = 0
            # 收集所有视频 URL
            if "video/mp4" in ct or "douyinvod.com" in url or ".mp4" in url:
                video_urls.append((url, cl))
            elif "play_addr" in url or ("video" in url and "play" in url):
                try:
                    body = await resp.json()
                    addr = body.get("play_addr", body)
                    url_list = addr.get("url_list", []) if isinstance(addr, dict) else []
                    if url_list:
                        video_urls.append((url_list[0], 0))
                except Exception:
                    pass

        page = await self.browser.new_page()
        try:
            page.on("response", lambda r: asyncio.ensure_future(on_response(r)))
            await page.goto(link, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(10000)  # 等足够耐俾完整视频加载
            # Play video to trigger full load
            try:
                await page.click("video", timeout=3000)
                await page.wait_for_timeout(3000)
            except Exception:
                pass
            # DOM <video> fallback
            try:
                src = await page.evaluate("() => {const v=document.querySelector('video');return v?v.src:'';}")
                if src and src not in [u for u, _ in video_urls]:
                    video_urls.append((src, 0))
            except Exception:
                pass
        finally:
            await page.close()

        if not video_urls:
            return ""
        # 按 content-length 降序，选最大嘅（真正视频，唔系加载动画）
        video_urls.sort(key=lambda x: x[1], reverse=True)
        best_url, best_size = video_urls[0]
        logger.info(f"douyin 视频候选: {len(video_urls)} 个, 选择 {best_size} bytes: {best_url[:100]}")
        return best_url

    # ── kuaishou ──────────────────────────────────────────

    async def _cover_kuaishou(self, item: dict) -> str:
        return item.get("cover_url", "")

    async def _video_kuaishou(self, item: dict) -> str:
        link = item.get("link", "") or f"https://www.kuaishou.com/photo/{item.get('photo_id', '')}"
        if not link:
            return ""
        captured_url = []

        async def on_response(resp):
            if captured_url:
                return
            if ".mp4" in resp.url or "video" in resp.url:
                captured_url.append(resp.url)

        page = await self.browser.new_page()
        try:
            page.on("response", lambda r: asyncio.ensure_future(on_response(r)))
            await page.goto(link, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(4000)
            if not captured_url:
                video_src = await page.evaluate("""() => {
                    const v = document.querySelector('video');
                    return v ? v.src : '';
                }""")
                if video_src:
                    captured_url.append(video_src)
        finally:
            await page.close()

        return captured_url[0] if captured_url else ""

    # ── bilibili ──────────────────────────────────────────

    async def _cover_bilibili(self, item: dict) -> str:
        cover = item.get("cover_url", "")
        if cover and cover.startswith("https://"):
            return cover
        # 兜底：浏览器提取 og:image
        link = item.get("link", "") or f"https://www.bilibili.com/video/{item.get('bvid', '')}"
        if not link:
            return ""
        try:
            page = await self.browser.new_page()
            try:
                await page.goto(link, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(2000)
                cover = await page.evaluate("""() => {
                    const meta = document.querySelector('meta[property="og:image"]');
                    return meta ? meta.getAttribute('content') : '';
                }""")
                return cover
            finally:
                await page.close()
        except Exception:
            return ""

    async def _video_bilibili(self, item: dict) -> str:
        bvid = item.get("bvid", "")
        if not bvid:
            return ""
        # Path 1: 纯 HTTP API（无需浏览器）
        try:
            from src.utils.bilibili_http import get_video_url
            url = await get_video_url(bvid)
            if url:
                return url
        except Exception:
            pass
        # Path 2: CDP 浏览器兜底
        link = item.get("link", "") or f"https://www.bilibili.com/video/{bvid}"
        captured_url = []
        async def on_response(resp):
            if captured_url: return
            if "mcdn.bilivideo" in resp.url or ("api.bilibili" in resp.url and "playurl" in resp.url):
                captured_url.append(resp.url)
        try:
            page = await self.browser.new_page()
            try:
                page.on("response", lambda r: asyncio.ensure_future(on_response(r)))
                await page.goto(link, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(3000)
                if not captured_url:
                    src = await page.evaluate("() => {const v=document.querySelector('video');return v?v.src:'';}")
                    if src: captured_url.append(src)
            finally:
                await page.close()
        except Exception:
            pass
        return captured_url[0] if captured_url else ""

    # ── xiaohongshu ───────────────────────────────────────

    async def _cover_xiaohongshu(self, item: dict) -> str:
        link = item.get("link", "")
        if not link:
            return ""
        page = await self.browser.new_page()
        try:
            await page.goto(link, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000)
            covers = await page.evaluate("""() => {
                const imgs = document.querySelectorAll('img.note-image, img[src*="xhscdn"], .note-content img');
                return Array.from(imgs).map(img => img.src).filter(Boolean);
            }""")
            return covers[0] if covers else ""
        finally:
            await page.close()

    async def _video_xiaohongshu(self, item: dict) -> str:
        link = item.get("link", "")
        if not link:
            return ""
        page = await self.browser.new_page()
        try:
            await page.goto(link, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000)
            video_src = await page.evaluate("""() => {
                const v = document.querySelector('video');
                return v ? v.src : '';
            }""")
            return video_src
        finally:
            await page.close()

    # ── zhihu ─────────────────────────────────────────────

    async def _cover_zhihu(self, item: dict) -> str:
        link = item.get("link", "")
        if not link:
            return ""
        page = await self.browser.new_page()
        try:
            await page.goto(link, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000)
            covers = await page.evaluate("""() => {
                const imgs = document.querySelectorAll('.RichContent img, .AnswerCard img');
                return Array.from(imgs).map(img => img.src).filter(Boolean);
            }""")
            return covers[0] if covers else ""
        finally:
            await page.close()

    async def _video_zhihu(self, item: dict) -> str:
        return ""  # 知乎极少视频


class MediaDownloader:
    """批量媒体下载器。"""

    def __init__(self, max_concurrent: int = None, max_file_mb: int = None):
        n = max_concurrent if max_concurrent is not None else settings.DOWNLOAD_MAX_CONCURRENT
        mb = max_file_mb if max_file_mb is not None else settings.DOWNLOAD_MAX_FILE_MB
        self._semaphore = asyncio.Semaphore(n)
        self._max_size = mb * 1024 * 1024
        self._client: httpx.AsyncClient | None = None
        self._extractor: MediaExtractor | None = None
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.douyin.com/",
        }

    async def _ensure_client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(120, connect=30),
                follow_redirects=True,
                headers=self._headers,
            )

    async def _ensure_extractor(self):
        if self._extractor is None:
            self._extractor = MediaExtractor()

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def download_items(
        self,
        items: list[dict],
        output_dir: str = None,
        topic: str = "",
        media_type: str = "all",
        progress_callback: callable = None,
    ) -> list[DownloadResult]:
        await self._ensure_client()
        await self._ensure_extractor()

        base = Path(output_dir or settings.DOWNLOAD_DIR)
        topic_safe = _safe_name(topic) if topic else "general"
        results: list[DownloadResult] = []

        want_cover = media_type in ("all", "cover")
        want_video = media_type in ("all", "video")

        urls_to_fetch: list[dict] = []

        for item in items:
            pid = item.get("platform", "unknown")
            iid = item.get("aweme_id") or item.get("photo_id") or item.get("bvid") or item.get("platform_id", "")
            link = item.get("link", "")

            if want_cover:
                cover_url = item.get("cover_url", "")
                if cover_url and cover_url.startswith("//"):
                    cover_url = "https:" + cover_url
                if not cover_url and link:
                    try:
                        cover_url = await self._extractor.extract_cover(pid, item)
                    except Exception:
                        pass
                if cover_url and not cover_url.startswith("blob:"):
                    ext = _ext_from_url(cover_url, ".jpg")
                    filepath = base / pid / topic_safe / f"cover_{_safe_name(iid)}{ext}"
                    urls_to_fetch.append({
                        "url": cover_url, "filepath": str(filepath),
                        "item_id": str(iid), "platform": pid, "media_type": "cover",
                    })

            if want_video:
                video_url = item.get("video_url", "")
                if not video_url and link:
                    video_url = await self._extractor.extract_video(pid, item)
                if video_url:
                    ext = _ext_from_url(video_url, ".mp4")
                    filepath = base / pid / topic_safe / f"video_{_safe_name(iid)}{ext}"
                    urls_to_fetch.append({
                        "url": video_url, "filepath": str(filepath),
                        "item_id": str(iid), "platform": pid, "media_type": "video",
                    })

        total = len(urls_to_fetch)
        tasks = []
        for uf in urls_to_fetch:
            tasks.append(self._download_one(**uf))

        if tasks:
            done = 0
            for coro in asyncio.as_completed(tasks):
                result = await coro
                results.append(result)
                done += 1
                if progress_callback:
                    progress_callback(done, total)

        return results

    async def download_urls(
        self,
        urls: list[str],
        output_dir: str = None,
        filenames: list[str] = None,
    ) -> list[DownloadResult]:
        await self._ensure_client()
        base = Path(output_dir or settings.DOWNLOAD_DIR)

        if filenames and len(filenames) == len(urls):
            names = filenames
        else:
            names = [f"download_{i}{_ext_from_url(u)}" for i, u in enumerate(urls)]

        tasks = []
        for url, name in zip(urls, names):
            tasks.append(self._download_one(
                url=url,
                filepath=str(base / name),
                item_id=name,
                platform="direct",
                media_type="file",
            ))

        results = []
        if tasks:
            for coro in asyncio.as_completed(tasks):
                results.append(await coro)
        return results

    async def _download_one(
        self,
        url: str,
        filepath: str,
        item_id: str = "",
        platform: str = "",
        media_type: str = "",
    ) -> DownloadResult:
        result = DownloadResult(
            item_id=item_id, platform=platform,
            media_type=media_type, url=url, filepath=filepath,
        )

        fp = Path(filepath)
        if fp.exists() and fp.stat().st_size > 0:
            result.status = "skipped"
            result.size_bytes = fp.stat().st_size
            return result

        fp.parent.mkdir(parents=True, exist_ok=True)

        # 最多重试 3 次，指数退避 1s/2s/4s
        for attempt in range(3):
            try:
                await self._ensure_client()
                tmp_path = fp.with_suffix(fp.suffix + ".tmp")
                if tmp_path.exists():
                    tmp_path.unlink()

                download_headers = {}
                if "hdslb.com" in url or "bilibili.com" in url:
                    download_headers["Referer"] = "https://www.bilibili.com/"
                elif "xhscdn.com" in url or "xiaohongshu.com" in url:
                    download_headers["Referer"] = "https://www.xiaohongshu.com/"
                elif "zhihu.com" in url:
                    download_headers["Referer"] = "https://www.zhihu.com/"

                async with self._client.stream("GET", url, headers=download_headers) as resp:
                    if resp.status_code not in (200, 206):
                        result.status = "failed"
                        result.error = f"HTTP {resp.status_code}"
                        if attempt < 2:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        return result

                    content_length = int(resp.headers.get("content-length", 0))
                    if content_length > self._max_size:
                        result.status = "failed"
                        result.error = f"文件 {content_length} 超过上限 {self._max_size}"
                        return result

                    with open(tmp_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
                            if f.tell() > self._max_size:
                                result.status = "failed"
                                result.error = f"下载超过上限 {self._max_size}"
                                try: tmp_path.unlink()
                                except Exception: pass
                                return result

                tmp_path.rename(fp)
                result.size_bytes = fp.stat().st_size
                result.status = "success"
                logger.info(f"下载完成: {fp.name} ({result.size_bytes} bytes)")
                return result

            except Exception as e:
                if attempt < 2:
                    logger.warning(f"下载重试 {attempt + 1}/3: {url[:80]} — {e}")
                    await asyncio.sleep(2 ** attempt)
                    continue
                result.status = "failed"
                result.error = str(e)[:100]
                logger.warning(f"下载失败: {url[:80]} — {e}")
                return result

        return result
