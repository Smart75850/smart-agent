import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

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
        dead = set()
        for ws in self._clients:
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        self._clients -= dead

    @property
    def connected_count(self) -> int:
        return len(self._clients)


broadcaster = LogBroadcaster()


class WebSocketLogHandler(logging.Handler):
    """Custom logging handler that broadcasts via WebSocket"""

    def __init__(self, broadcaster: LogBroadcaster, level=logging.INFO):
        super().__init__(level)
        self._broadcaster = broadcaster

    def emit(self, record: logging.LogRecord):
        try:
            data = {
                "time": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                "level": record.levelname,
                "message": record.getMessage(),
            }
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._broadcaster.broadcast(data))
        except Exception:
            self.handleError(record)


# Register the WebSocket log handler globally
_log_handler = WebSocketLogHandler(broadcaster)
_log_handler.setLevel(logging.INFO)
logging.getLogger("smart-agent").addHandler(_log_handler)
logging.getLogger().addHandler(_log_handler)


@router.websocket("/api/ws")
async def log_websocket(ws: WebSocket):
    await ws.accept()
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
