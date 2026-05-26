"""CookieBridge — Chrome Extension 登录态同步。

localhost:18920 HTTP 服务，接收 Chrome Extension POST 的 cookies，
保存到 browser_data/{platform}_cookies.json。

用法:
    python main.py --cookie-bridge
    然后在 Chrome Extension 弹窗中点击「同步」
"""

import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from src.utils.logger import logger

PORT = 18920
HOST = "127.0.0.1"
OUTPUT_DIR = Path("browser_data")

# sameSite 映射：Chrome API 底线格式 → Playwright 大写格式
_SAMESITE_MAP = {
    "no_restriction": "None",
    "lax": "Lax",
    "strict": "Strict",
    "unspecified": "Lax",
}


def _filter_valid_cookies(cookies: list[dict]) -> list[dict]:
    """过滤过期 cookie + 标准化字段。"""
    now = time.time()
    valid = []
    for c in cookies:
        exp = c.get("expirationDate")
        # 跳过已过期的持久化 cookie
        if exp and exp < now:
            continue
        valid.append({
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": c.get("domain", ""),
            "path": c.get("path", "/"),
            "expires": exp if exp else -1,           # -1 = session cookie
            "httpOnly": c.get("httpOnly", False),
            "secure": c.get("secure", False),
            "sameSite": _SAMESITE_MAP.get(c.get("sameSite", ""), "Lax"),
        })
    return valid


class _CookieHandler(BaseHTTPRequestHandler):

    def _cors_headers(self):
        origin = self.headers.get("Origin", "")
        if origin.startswith("chrome-extension://") or origin.startswith("moz-extension://"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self._cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path != "/cookies":
            self.send_response(404)
            self.end_headers()
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)

            platform = data.get("platform", "")
            raw_cookies = data.get("cookies", [])

            if not platform:
                self._respond_json(400, {"ok": False, "error": "缺少 platform"})
                return

            cookies = _filter_valid_cookies(raw_cookies)

            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            filepath = OUTPUT_DIR / f"{platform}_cookies.json"
            filepath.write_text(
                json.dumps(cookies, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            logger.info(f"CookieBridge: {platform} 接收 {len(raw_cookies)} 个，有效 {len(cookies)} 个 → {filepath}")
            self._respond_json(200, {"ok": True, "platform": platform, "saved": len(cookies)})

        except Exception as exc:
            logger.warning(f"CookieBridge POST 失败: {exc}")
            self._respond_json(500, {"ok": False, "error": str(exc)})

    def _respond_json(self, status: int, data: dict):
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def log_message(self, format, *args):
        """重定向到项目 logger，避免 stdout 混乱。"""
        logger.debug(f"CookieBridge HTTP: {args[0]}")


def start_server(host: str = HOST, port: int = PORT):
    server = HTTPServer((host, port), _CookieHandler)
    print(f"CookieBridge 服务已启动: http://{host}:{port}")
    print("请在 Chrome Extension 弹窗中点击「同步」按钮")
    print("按 Ctrl+C 停止服务")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCookieBridge 服务已停止")
    finally:
        server.server_close()
