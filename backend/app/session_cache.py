"""Active session tracking.

Sessions are the authoritative record in the auth store; this module keeps
hot session metadata in Redis (when available) with an in-memory fallback so
the app always works without infrastructure services. TTLs mirror the
session ``expires_at`` so stale keys self-expire.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any

from .config import settings

SESSION_CACHE_PREFIX = "satquery:session:"
session_lifetime = 0  # populated once the auth store is created


def _ttl_for_session(session: dict) -> int:
    """Seconds until ``expires_at`` (minimum 1, capped at 60 days)."""
    try:
        from .storage import datetime_now

        expires = session.get("expires_at")
        if not expires:
            return 86400
        from datetime import datetime, timezone

        exp = datetime.fromisoformat(expires)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        ttl = int((exp - datetime.now(timezone.utc)).total_seconds())
        return max(1, min(ttl, 60 * 24 * 3600))
    except Exception:
        return 86400


class SessionCache:
    """Duck-typed cache: ``set`` / ``get`` / ``delete`` / ``ping``."""

    def provided(self) -> bool:
        raise NotImplementedError

    def set(self, session_id: str, payload: dict, ttl: int) -> None:
        raise NotImplementedError

    def get(self, session_id: str) -> dict | None:
        raise NotImplementedError

    def delete(self, session_id: str) -> None:
        raise NotImplementedError


class RedisSessionCache(SessionCache):
    _instance: "RedisSessionCache | None" = None

    def __init__(self, redis_client: Any):
        self._redis = redis_client

    def provided(self) -> bool:
        return True

    def set(self, session_id: str, payload: dict, ttl: int) -> None:
        try:
            self._redis.setex(
                f"{SESSION_CACHE_PREFIX}{session_id}",
                ttl,
                json.dumps(payload, default=str),
            )
        except Exception:
            pass

    def get(self, session_id: str) -> dict | None:
        try:
            raw = self._redis.get(f"{SESSION_CACHE_PREFIX}{session_id}")
            return json.loads(raw) if raw else None
        except Exception:
            return None

    def delete(self, session_id: str) -> None:
        try:
            self._redis.delete(f"{SESSION_CACHE_PREFIX}{session_id}")
        except Exception:
            pass


class MemorySessionCache(SessionCache):
    """Thread-safe process-local fallback (single worker deployments)."""

    _instance: "MemorySessionCache | None" = None

    def __init__(self) -> None:
        self._data: dict[str, tuple[dict, float]] = {}
        self._lock = threading.Lock()

    def provided(self) -> bool:
        return False

    def _prune(self) -> None:
        now = time.monotonic()
        dead = [k for k, (_, exp) in self._data.items() if exp <= now]
        for k in dead:
            self._data.pop(k, None)

    def set(self, session_id: str, payload: dict, ttl: int) -> None:
        with self._lock:
            self._data[session_id] = (payload, time.monotonic() + max(ttl, 1))

    def get(self, session_id: str) -> dict | None:
        with self._lock:
            self._prune()
            item = self._data.get(session_id)
            return dict(item[0]) if item else None

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._data.pop(session_id, None)


_cache: SessionCache | None = None
_cache_probe_done = False


def get_session_cache() -> SessionCache:
    """Return the shared cache, probing for Redis once on first use."""
    global _cache, _cache_probe_done
    if _cache is not None:
        return _cache
    if not _cache_probe_done:
        _cache_probe_done = True
        if settings.REDIS_ENABLED in ("on", "auto"):
            try:
                import redis  # type: ignore

                client = redis.Redis.from_url(
                    settings.REDIS_URL,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                    decode_responses=True,
                )
                client.ping()
                print(f"[satquery] session cache: Redis ({settings.REDIS_URL})")
                _cache = RedisSessionCache(client)
                return _cache
            except Exception as exc:
                if settings.REDIS_ENABLED == "on":
                    raise RuntimeError(f"Redis required (REDIS_ENABLED=on) but unreachable: {exc}") from exc
                print("[satquery] Redis unreachable - using in-memory session cache.")
        if settings.REDIS_ENABLED == "off":
            print("[satquery] REDIS_ENABLED=off - using in-memory session cache.")
        _cache = MemorySessionCache()
    return _cache


def reset_session_cache_for_tests() -> None:
    global _cache, _cache_probe_done
    _cache = None
    _cache_probe_done = False