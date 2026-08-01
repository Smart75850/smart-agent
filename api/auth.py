"""Smart Agent API 鉴权中间件。

API_TOKEN 未设置时（本机开发模式）所有请求放行；
设置后除白名单路径外，所有 HTTP 请求需携带 `Authorization: Bearer <token>`。
WebSocket 鉴权走 query 参数 token（由 ws 路由调用 check_ws_token）。
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config.settings import settings

# 无需鉴权的公开路径（文档 + WebUI 页面本身）
PUBLIC_PATHS = ("/docs", "/redoc", "/openapi.json", "/health", "/")


class AuthMiddleware(BaseHTTPMiddleware):
    """Bearer Token 鉴权中间件。"""

    async def dispatch(self, request: Request, call_next):
        # 未配置 API_TOKEN → 本机模式，全部放行（服务默认只绑 127.0.0.1）
        if not settings.API_TOKEN or request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and auth[7:].strip() == settings.API_TOKEN:
            return await call_next(request)

        return JSONResponse(
            status_code=401,
            content={"error": "unauthorized", "message": "缺少或无效的 API Token"},
        )


def check_ws_token(token: str | None) -> bool:
    """WebSocket 鉴权：校验 query 参数 token。未配置 API_TOKEN 时放行。"""
    if not settings.API_TOKEN:
        return True
    return bool(token) and token == settings.API_TOKEN
