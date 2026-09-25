"""Request logging + rate limiting middleware.

* Every request is logged to console and `backend/data/satquery.log`.
* A sliding-window in-memory rate limiter protects public & auth endpoints.
"""
from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from ..config import settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(module)s:%(lineno)d | %(message)s"
_SENSITIVE_LOG_VALUE = re.compile(
    r"(?i)([?&](?:token|access_token|refresh_token|session_token|session_id|password|otp|code)=)([^&#\s]+)"
)
_BEARER_VALUE = re.compile(r"(?i)(bearer\s+)[^\s,;]+")


def redact_sensitive_log_text(value: object) -> str:
    """Redact credentials carried in URLs or accidentally formatted log text."""
    text = str(value)
    text = _SENSITIVE_LOG_VALUE.sub(r"\1[REDACTED]", text)
    return _BEARER_VALUE.sub(r"\1[REDACTED]", text)


class SensitiveLogFilter(logging.Filter):
    """Apply URL/token redaction before an application or Uvicorn handler emits.

    When a record carries formatting arguments (e.g. uvicorn's access log:
    ``'%s - "%s %s HTTP/%s" %d'`` with a URL in the args) the arguments are
    redacted in place and the tuple is preserved, because Uvicorn's
    ``AccessFormatter`` requires the original arg count to re-render the line.
    Collapsing the message and emptying ``args`` (as older versions did) made
    uvicorn's formatter raise on every request.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if record.args:
                record.args = tuple(
                    redact_sensitive_log_text(a) if isinstance(a, str) else a
                    for a in record.args
                )
            else:
                record.msg = redact_sensitive_log_text(record.getMessage())
        except Exception:
            record.msg = str(record.msg)
        return True

logger = logging.getLogger("satquery")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    try:
        settings.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(settings.LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        logger.addHandler(file_handler)
    except Exception:  # pragma: no cover
        pass

    logger.propagate = False

# Uvicorn logs WebSocket request targets through its separate access logger.
# Attach the same filter to its handlers without changing authentication.
_sensitive_log_filter = SensitiveLogFilter()
for _logger_name in ("satquery", "uvicorn", "uvicorn.access", "uvicorn.error"):
    _logger = logging.getLogger(_logger_name)
    _logger.addFilter(_sensitive_log_filter)
    for _handler in _logger.handlers:
        _handler.addFilter(_sensitive_log_filter)


class RateLimiter:
    """Thread-safe sliding window counter keyed by (scope, ip)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, scope: str, ip: str, limit: int, window_seconds: int = 60) -> bool:
        key = f"{scope}:{ip}"
        now = time.monotonic()
        with self._lock:
            dq = self._hits[key]
            while dq and now - dq[0] > window_seconds:
                dq.popleft()
            if len(dq) >= limit:
                return False
            dq.append(now)
            return True


_limiter = RateLimiter()


def reset_rate_limit_for_tests():
    """Clear in-memory rate-limit windows (used by the pytest suite)."""
    _limiter._hits.clear()


def setup_logging():
    return logger


class LoggingAndRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        request_id = request.headers.get("x-request-id", uuid.uuid4().hex[:12])
        request.state.request_id = request_id
        ip = request.client.host if request.client else "unknown"
        path = request.url.path

        # Rate limiting for sensitive scopes
        if settings.RATE_LIMIT_ENABLED:
            path_prefix = path
            if path.startswith(
                (
                    "/api/auth/login",
                    "/api/auth/register",
                    "/api/auth/forgot",
                    "/api/auth/reset",
                    "/api/v1/auth/login",
                    "/api/v1/auth/register",
                    "/api/v1/auth/verify-email",
                    "/api/v1/auth/mfa/challenge",
                )
            ):
                allowed = _limiter.hit("auth", ip, settings.RATE_LIMIT_AUTH_PER_MINUTE)
            elif path.startswith(("/api/v1/auth/change-password", "/api/auth/change-password")):
                # 5 attempts / 5 minutes for password re-verification.
                allowed = _limiter.hit("password", ip, 5, 300)
            else:
                allowed = _limiter.hit("api", ip, settings.RATE_LIMIT_PER_MINUTE)
            if not allowed:
                logger.warning("rate-limited %s %s from %s", request.method, path, ip)
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Too many requests. Please slow down and try again in a minute.",
                        "code": "RATE_LIMITED",
                    },
                )

        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        if path.startswith("/api"):
            logger.info(
                "%s %s -> %s (%d ms) [%s] %s",
                request.method,
                path,
                response.status_code,
                round(duration_ms, 1),
                request_id,
                ip,
            )
        return response
