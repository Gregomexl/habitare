"""ConnectionManager — in-process WebSocket registry keyed by tenant_id.

This is a module-level singleton. Import and use `ws_manager` directly.
"""
import uuid
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        # tenant_id (str) → list of connected WebSockets
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, tenant_id: uuid.UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[str(tenant_id)].append(websocket)

    def disconnect(self, tenant_id: uuid.UUID, websocket: WebSocket) -> None:
        key = str(tenant_id)
        if websocket in self._connections[key]:
            self._connections[key].remove(websocket)

    async def broadcast(self, tenant_id: uuid.UUID, message: dict) -> None:
        """Send message to all connected staff in a tenant. Fire-and-forget."""
        import json
        import logging
        logger = logging.getLogger(__name__)
        key = str(tenant_id)
        dead = []
        for ws in list(self._connections[key]):
            try:
                await ws.send_text(json.dumps(message))
            except Exception as exc:
                logger.warning("WebSocket send failed, removing connection: %s", exc)
                dead.append(ws)
        for ws in dead:
            self.disconnect(tenant_id, ws)


# Module-level singleton
ws_manager = ConnectionManager()
