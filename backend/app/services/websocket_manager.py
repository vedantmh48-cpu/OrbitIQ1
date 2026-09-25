"""WebSocket connection managers.

* Job progress streaming on ``/ws/jobs/{job_id}``.
* Per-user security notifications on ``/ws/notifications/{user_id}``
  (``session_revoked`` / ``password_changed`` events that force other tabs
  and devices to sign out immediately).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._jobs: dict[str, set[WebSocket]] = {}
        self._users: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    # --- job channels -----------------------------------------------------

    async def connect(self, job_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._jobs.setdefault(job_id, set()).add(ws)

    async def disconnect(self, job_id: str, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._jobs.get(job_id, set())
            conns.discard(ws)
            if not conns:
                self._jobs.pop(job_id, None)

    async def broadcast(self, job_id: str, message: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._jobs.get(job_id, set()))
        dead = []
        payload = json.dumps(message, default=str)
        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(job_id, ws)

    # --- per-user notification channels -----------------------------------

    async def connect_user(self, user_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._users.setdefault(user_id, set()).add(ws)

    async def disconnect_user(self, user_id: str, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._users.get(user_id, set())
            conns.discard(ws)
            if not conns:
                self._users.pop(user_id, None)

    async def send_to_user(self, user_id: str, message: dict[str, Any]) -> int:
        """Deliver an event to every live socket for a user. Returns count."""
        async with self._lock:
            targets = list(self._users.get(user_id, set()))
        dead = []
        payload = json.dumps(message, default=str)
        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect_user(user_id, ws)
        return len(targets) - len(dead)

    async def notify_user(self, user_id: str, event_type: str, **data) -> int:
        return await self.send_to_user(
            user_id, {"type": event_type, "ts": _utc_now(), **data}
        )


def _utc_now() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat()


manager = ConnectionManager()


def notify_user(user_id: str, event_type: str, **data):
    """Fire-and-forget wrapper so sync route handlers can broadcast."""

    async def _deliver():
        try:
            await manager.notify_user(user_id, event_type, **data)
        except Exception:
            pass

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # no running loop (e.g. worker thread with no loop owner)
    try:
        loop.create_task(_deliver())
    except RuntimeError:
        pass