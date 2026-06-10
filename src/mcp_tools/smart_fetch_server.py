#!/usr/bin/env python3
"""
Smart Fetch MCP Server
======================
通用 URL 抓取工具 — 用 curl_cffi TLS 指纹伪装 + 浏览器 UA 突破反爬。
支援知乎、微信公众号、CSDN、掘金等常见中文站点。

用法（MCP 配置）:
  {
    "smart-fetch": {
      "command": "python",
      "args": ["C:/Users/guohu/workspace/smart-agent/src/mcp_tools/smart_fetch_server.py"]
    }
  }
"""

import json
import os
import sys
import re
from html.parser import HTMLParser

try:
    from curl_cffi import requests
    HAS_CURL_CFFI = True
except ImportError:
    import httpx
    HAS_CURL_CFFI = False

# 🆕 反反爬自動升級
from src.utils.anti_bot_escalator import AntiBotEscalator, EscalationLevel


class TextExtractor(HTMLParser):
    """从 HTML 提取纯文本"""
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip_tags = {'script', 'style', 'nav', 'footer', 'header', 'code', 'pre'}
        self.current_tag = None

    def handle_starttag(self, tag, attrs):
        self.current_tag = tag

    def handle_endtag(self, tag):
        self.current_tag = None

    def handle_data(self, data):
        if self.current_tag not in self.skip_tags:
            t = data.strip()
            if t and len(t) > 1:
                self.text.append(t)


def _fetch_cdp(url: str, timeout: int = 30) -> dict:
    """CDP/Playwright 回退 — 適用於反爬站點（知乎/CSDN/微信等），需要 Chrome CDP 先行啟動。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "url": url, "error": "Playwright not installed", "content": "", "content_type": "", "status_code": 0}

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp('http://127.0.0.1:9222', timeout=min(timeout, 10) * 1000)
            page = browser.contexts[0].new_page()
            page.goto(url, timeout=timeout * 1000, wait_until='domcontentloaded')
            page.wait_for_timeout(4000)

            # 嘗試提取文章正文
            text = ""
            selectors = ['.Post-RichText', '.RichText', 'article', '[class*="article"]',
                         '[class*="Post"]', '[class*="content"]', '.markdown-body']
            for sel in selectors:
                el = page.query_selector(sel)
                if el:
                    t = el.inner_text()
                    if len(t) > 100:
                        text = t
                        break
            if not text or len(text) < 50:
                text = page.inner_text('body')

            # 限制長度
            if len(text) > 8000:
                text = text[:8000] + f"\n\n... [截斷，原文 {len(text)} 字符]"

            page.close()
            return {
                "ok": True, "url": url, "content": text,
                "content_type": "text/plain; via-cdp",
                "status_code": 200, "length": len(text),
            }
    except Exception as e:
        return {"ok": False, "url": url, "error": f"CDP: {e}", "content": "", "content_type": "", "status_code": 0}


def smart_fetch(url: str, headers: dict = None, timeout: int = 30) -> dict:
    """
    抓取 URL 内容 — 使用 SmartFetcher 三層架構。

    auto 模式：先 Light (HTTP) → 檢測封鎖 → 被封自動升 Stealth (瀏覽器)
    層內全自動處理 TLS 偽裝、CF 破解、廣告攔截等。

    Args:
        url: 目标 URL
        headers: 自定义请求头（仅 light 模式）（可选）
        timeout: 超时秒数（默认 30）

    Returns:
        {"ok": true/false, "url": ..., "content": ..., "content_type": ..., "status_code": ..., "error": ...}
    """
    import asyncio
    from src.fetchers import SmartFetcher

    async def _fetch():
        return await SmartFetcher.fetch(
            url,
            mode="auto",
            headers=headers,
            timeout=timeout,
        )

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _fetch())
                return future.result(timeout=timeout * 2)
        else:
            return asyncio.run(_fetch())
    except RuntimeError:
        return asyncio.run(_fetch())


# ====== MCP Server (FastMCP 兼容 / stdio 模式) ======

def serve_stdio():
    """简易 stdio JSON-RPC MCP 服务器"""
    import select  # Windows: 仅用于检测 stdin

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            request = json.loads(line.strip())

            method = request.get("method", "")
            req_id = request.get("id")

            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "smart-fetch", "version": "1.0.0"}
                    }
                }
            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": [{
                            "name": "smart_fetch",
                            "description": "抓取任意 URL 内容。使用 TLS 指纹伪装 + 浏览器 UA 突破反爬。支持知乎、微信公众号、CSDN、掘金等常见中文站点。返回纯文本内容（HTML 自动提取）。",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "url": {"type": "string", "description": "目标 URL"},
                                    "headers": {"type": "object", "description": "自定义请求头（可选）"},
                                    "timeout": {"type": "integer", "description": "超时秒数，默认30"},
                                },
                                "required": ["url"]
                            }
                        }]
                    }
                }
            elif method == "tools/call":
                params = request.get("params", {})
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})

                if tool_name == "smart_fetch":
                    result = smart_fetch(
                        url=arguments.get("url", ""),
                        headers=arguments.get("headers"),
                        timeout=arguments.get("timeout", 30),
                    )
                    response = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
                        }
                    }
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
                    }
            elif method == "notifications/initialized":
                continue  # 通知不需要响应
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown method: {method}"}
                }

            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()

        except json.JSONDecodeError:
            continue
        except Exception as e:
            err_resp = {
                "jsonrpc": "2.0",
                "id": req_id if 'req_id' in dir() else None,
                "error": {"code": -32603, "message": str(e)}
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    serve_stdio()
