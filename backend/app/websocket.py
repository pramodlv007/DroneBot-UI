"""
UI-facing WebSocket fan-out. One `/ws` connection per UI client; the server
pushes typed {"topic": ..., "data": ...} envelopes for the topics listed in
§31 (robot_state, coordination_state, mission_state, system_health, events,
supervisor_state). Clients never publish robot commands over this socket —
all commands are REST POSTs (see routers/*_api.py) so every command is
independently authorizable/auditable and the WS stays a pure telemetry
sink, satisfying §46's "prevent arbitrary ... publication from browser
users."
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket


class UIConnectionManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, topic: str, data: Any) -> None:
        if not self._clients:
            return
        payload = json.dumps({"topic": topic, "data": data}, default=str)
        dead: list[WebSocket] = []
        async with self._lock:
            clients = list(self._clients)
        for ws in clients:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)
