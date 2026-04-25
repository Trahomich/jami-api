import asyncio
import json
from typing import Any

import structlog
from fastapi import WebSocket

logger = structlog.get_logger()


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, account_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        if account_id not in self._connections:
            self._connections[account_id] = []
        self._connections[account_id].append(websocket)
        logger.info("ws_connected", account_id=account_id)

    def disconnect(self, account_id: str, websocket: WebSocket) -> None:
        if account_id in self._connections:
            self._connections[account_id].remove(websocket)
            if not self._connections[account_id]:
                del self._connections[account_id]
        logger.info("ws_disconnected", account_id=account_id)

    async def broadcast(self, account_id: str, data: Any) -> None:
        connections = self._connections.get(account_id, [])
        dead: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(account_id, ws)
