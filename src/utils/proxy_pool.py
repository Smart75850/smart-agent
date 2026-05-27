"""代理池 — 轮转 + 健康检测 + 失败剔除。"""
import asyncio, json, logging, random, time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

PROXY_FILE = Path(__file__).resolve().parent.parent.parent / "config/proxies.json"


class Proxy:
    __slots__ = ("url", "protocol", "host", "port", "failures", "last_used", "last_check")
    def __init__(self, url: str):
        self.url = url
        parsed = urlparse(url)
        self.protocol = parsed.scheme
        self.host = parsed.hostname or ""
        self.port = parsed.port or 0
        self.failures = 0
        self.last_used = 0.0
        self.last_check = 0.0

    @property
    def is_healthy(self) -> bool:
        return self.failures < 3

    def mark_success(self):
        self.failures = 0
        self.last_used = time.time()

    def mark_failure(self):
        self.failures += 1
        self.last_used = time.time()


class ProxyPool:
    """代理池单例 — 轮转 + 自动健康检测。"""
    _instance: Optional["ProxyPool"] = None

    def __init__(self):
        self._proxies: list[Proxy] = []
        self._index = 0
        self._check_interval = 300  # 5 分钟健康检测间隔
        self._load()

    @classmethod
    def get(cls) -> "ProxyPool":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load(self):
        if not PROXY_FILE.exists():
            logger.info("[proxy-pool] 未找到配置文件，代理池为空（直连模式）")
            return
        try:
            data = json.loads(PROXY_FILE.read_text("utf-8"))
            urls = data.get("proxies", []) if isinstance(data, dict) else data
            self._proxies = [Proxy(u) for u in urls if isinstance(u, str) and u.strip()]
            logger.info(f"[proxy-pool] 加载 {len(self._proxies)} 个代理")
        except Exception as exc:
            logger.warning(f"[proxy-pool] 加载失败: {exc}")

    def add(self, proxy_url: str):
        if proxy_url not in {p.url for p in self._proxies}:
            self._proxies.append(Proxy(proxy_url))

    def remove(self, proxy_url: str):
        self._proxies = [p for p in self._proxies if p.url != proxy_url]

    @property
    def size(self) -> int:
        return len(self._proxies)

    @property
    def healthy_count(self) -> int:
        return sum(1 for p in self._proxies if p.is_healthy)

    def get_next(self) -> Optional[Proxy]:
        """轮转获取下一个健康代理。"""
        healthy = [p for p in self._proxies if p.is_healthy]
        if not healthy:
            return None
        self._index = (self._index + 1) % len(healthy)
        return healthy[self._index]

    def get_random(self) -> Optional[Proxy]:
        """随机获取一个健康代理。"""
        healthy = [p for p in self._proxies if p.is_healthy]
        return random.choice(healthy) if healthy else None

    def get_httpx_proxy(self) -> Optional[str]:
        """获取 httpx 格式的代理 URL。"""
        proxy = self.get_next()
        return proxy.url if proxy else None

    async def check_health(self, proxy: Proxy, timeout: float = 10) -> bool:
        """检查单个代理是否可达。"""
        if time.time() - proxy.last_check < self._check_interval:
            return proxy.is_healthy
        try:
            test_urls = ["https://httpbin.org/ip", "https://api.ipify.org?format=json"]
            test_url = test_urls[hash(proxy.url) % len(test_urls)]
            async with httpx.AsyncClient(proxy=proxy.url, timeout=timeout) as client:
                resp = await client.get(test_url)
                ok = 200 <= resp.status_code < 400
                if ok:
                    proxy.mark_success()
                else:
                    proxy.mark_failure()
                proxy.last_check = time.time()
                return ok
        except:
            proxy.mark_failure()
            proxy.last_check = time.time()
            return False

    async def check_all(self) -> dict[str, int]:
        """检测全部代理健康状态。"""
        healthy, dead = 0, 0
        for proxy in self._proxies:
            ok = await self.check_health(proxy)
            if ok:
                healthy += 1
            else:
                dead += 1
        logger.info(f"[proxy-pool] 健康检测完成: {healthy} OK, {dead} FAIL")
        return {"healthy": healthy, "dead": dead}

    def status(self) -> dict:
        return {
            "total": self.size,
            "healthy": self.healthy_count,
            "dead": self.size - self.healthy_count,
            "proxies": [{"url": p.url[:50] + "..." if len(p.url) > 50 else p.url,
                         "failures": p.failures, "healthy": p.is_healthy}
                        for p in self._proxies],
        }

    def create_proxy_config(self) -> Optional[str]:
        """创建示例配置文件。"""
        PROXY_FILE.parent.mkdir(parents=True, exist_ok=True)
        example = {
            "proxies": [
                "http://user:pass@proxy1.example.com:8080",
                "http://proxy2.example.com:3128",
                "socks5://127.0.0.1:1080",
            ],
            "_说明": "支持 http/https/socks5 代理，留空数组则直连",
        }
        PROXY_FILE.write_text(json.dumps(example, ensure_ascii=False, indent=2), "utf-8")
        return str(PROXY_FILE)


# 全局单例
proxy_pool = ProxyPool.get()
