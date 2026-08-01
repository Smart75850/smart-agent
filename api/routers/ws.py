import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.auth import check_ws_token

router = APIRouter()


class LogBroadcaster:
    """WebSocket log broadcast manager (singleton)"""

    def __init__(self):
        self._clients: set[WebSocket] = set()

    def add(self, ws: WebSocket):
        self._clients.add(ws)

    def remove(self, ws: WebSocket):
        self._clients.discard(ws)

    async def broadcast(self, data: dict):
        # 先快照再遍历，避免 await 期间被其他协程 disconnect 修改集合导致 RuntimeError
        for ws in list(self._clients):
            try:
                await ws.send_json(data)
            except Exception:
                self._clients.discard(ws)

    @property
    def connected_count(self) -> int:
        return len(self._clients)


broadcaster = LogBroadcaster()


class WebSocketLogHandler(logging.Handler):
    """Custom logging handler that broadcasts via WebSocket"""

    def __init__(self, broadcaster: LogBroadcaster, level=logging.INFO):
        super().__init__(level)
        self._broadcaster = broadcaster
        self._main_loop: asyncio.AbstractEventLoop | None = None

    def capture_loop(self):
        try:
            self._main_loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

    def emit(self, record: logging.LogRecord):
        loop = self._main_loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
                self._main_loop = loop
            except RuntimeError:
                return
        # 事件循环已关闭时直接丢弃，避免投递永不执行的 coroutine 触发资源泄漏告警
        if loop.is_closed():
            return
        try:
            data = {
                "time": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                "level": record.levelname,
                "message": record.getMessage(),
            }
            asyncio.run_coroutine_threadsafe(
                self._broadcaster.broadcast(data), loop
            )
        except Exception:
            self.handleError(record)


# Register the WebSocket log handler globally
_log_handler = WebSocketLogHandler(broadcaster)
_log_handler.setLevel(logging.INFO)
logging.getLogger("smart-agent").addHandler(_log_handler)
logging.getLogger().addHandler(_log_handler)


@router.websocket("/api/ws")
async def log_websocket(ws: WebSocket):
    # 鉴权：配置了 API_TOKEN 时必须带 ?token=xxx，否则拒绝连接
    if not check_ws_token(ws.query_params.get("token")):
        await ws.close(code=4401)
        return
    await ws.accept()
    _log_handler.capture_loop()
    broadcaster.add(ws)
    try:
        # Send initial connection confirmation
        await ws.send_json({
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": "SYSTEM",
            "message": f"已連接 — {broadcaster.connected_count} 個 client",
        })
        # Keep connection alive; receive loop to detect disconnect
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                # Send ping-like keepalive
                await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        broadcaster.remove(ws)
