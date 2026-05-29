"""Smart Agent Pro - 使用额度 API 中间件。

在每次 crawl/pipeline 请求前检查额度。
"""
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.utils.usage_tracker import check_quota, consume_one, get_status, activate_pro


class UsageMiddleware(BaseHTTPMiddleware):
    """使用额度检查中间件。"""

    # 需要消耗额度的路径
    QUOTA_PATHS = ["/api/crawl", "/api/pipeline"]

    # 不需要检查的路径（白名单）
    SKIP_PATHS = ["/api/platforms", "/api/config", "/api/data", "/api/ws",
                  "/api/usage", "/api/activate", "/health", "/docs", "/openapi.json"]

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 跳过不需要检查的路径
        if any(path.startswith(skip) for skip in self.SKIP_PATHS):
            return await call_next(request)

        # 只检查 POST 请求到 crawl/pipeline
        if request.method == "POST" and any(path.startswith(q) for q in self.QUOTA_PATHS):
            quota = check_quota()
            if not quota["allowed"]:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "quota_exceeded",
                        "message": quota["message"],
                        "remaining": 0,
                        "wechat": "smart4906"
                    }
                )
            # 消耗一次额度
            result = consume_one()

        return await call_next(request)
