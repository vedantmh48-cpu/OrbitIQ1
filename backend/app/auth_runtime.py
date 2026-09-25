"""Shared runtime helpers for the v1 auth vertical slice.

Bridges the auth store, the active-session cache and the per-user
notification WebSockets so both route handlers and the ``get_current_user``
dependency behave identically.
"""
from __future__ import annotations

import datetime as dt
import re
import threading
import time

from .auth_store import get_auth_store, normalize_user
from .config import settings
from .security import create_access_token, hash_refresh_token, new_refresh_token
from .services.websocket_manager import notify_user
from .session_cache import get_session_cache

# ---------------------------------------------------------------------------
# Error codes surfaced to the client (``detail`` + ``code`` envelope).
# ---------------------------------------------------------------------------

ERR_EMAIL_NOT_VERIFIED = "EMAIL_NOT_VERIFIED"
ERR_MFA_REQUIRED = "MFA_REQUIRED"
ERR_MFA_SETUP_REQUIRED = "MFA_SETUP_REQUIRED"
ERR_MFA_INVALID = "MFA_INVALID"
ERR_SESSION_REVOKED = "SESSION_REVOKED"
ERR_SESSION_EXPIRED = "SESSION_EXPIRED"
ERR_SESSION_INACTIVE = "SESSION_INACTIVE"
ERR_NOT_AUTHENTICATED = "UNAUTHENTICATED"

_UA_BROWSERS = (
    ("Edg/", "Edge"),
    ("OPR/", "Opera"),
    ("Firefox/", "Firefox"),
    ("Chrome/", "Chrome"),
    ("Safari/", "Safari"),
)
_UA_OS = (
    ("Windows NT 10", "Windows 10/11"),
    ("Windows NT 6.1", "Windows 7"),
    ("Mac OS X", "macOS"),
    ("Android", "Android"),
    ("iPhone", "iOS"),
    ("iPad", "iPadOS"),
    ("Linux", "Linux"),
)


def device_label_from_ua(user_agent: str) -> str:
    ua = user_agent or ""
    browser = "Browser"
    for token, label in _UA_BROWSERS:
        if token in ua:
            browser = label
            break
    os_name = "Device"
    for token, label in _UA_OS:
        if token in ua:
            os_name = label
            break
    return f"{browser} · {os_name}"


def client_ip(request) -> str:
    """Best-effort real client IP (respects X-Forwarded-For)."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first and not first.lower().startswith("unknown"):
            return first
    return request.client.host if request.client else "127.0.0.1"


# ---------------------------------------------------------------------------
# Security notification e-mails ("new sign-in" alerts)
# ---------------------------------------------------------------------------


def login_notification_enabled(user: dict) -> bool:
    """Global switch **and** the per-user ``notifications.security_alerts`` pref."""
    if not settings.LOGIN_NOTIFICATION_ENABLED:
        return False
    prefs = (user.get("settings") or {}).get("notifications") or {}
    return bool(prefs.get("security_alerts", True))


def _login_notification_context(user: dict, request=None, mfa_used: bool = False) -> dict | None:
    """Return safe notification arguments only when this user may be alerted."""
    if not user or not user.get("email"):
        return None
    if not user.get("email_verified", False):
        return None
    if not login_notification_enabled(user):
        return None
    return {
        "to_email": user["email"],
        "name": user.get("name", ""),
        "device_label": device_label_from_ua(request.headers.get("user-agent", ""))
        if request is not None
        else "",
        "ip_address": client_ip(request) if request is not None else "",
        "mfa_used": mfa_used,
    }


def notify_login_email(user: dict, request=None, mfa_used: bool = False) -> dict:
    """E-mail a "new sign-in" alert after a successful login.

    Best-effort: any delivery problem is logged by the mailer and reported in
    the returned dict - it never blocks or fails the sign-in itself. Only
    verified addresses receive security alerts, and users can opt out through
    ``settings.notifications.security_alerts``.
    """
    from .auth_otp import send_login_notification

    context = _login_notification_context(user, request, mfa_used)
    if not user or not user.get("email"):
        return {"sent": False, "skipped": "no_email"}
    if not user.get("email_verified", False):
        return {"sent": False, "skipped": "email_unverified"}
    if not login_notification_enabled(user):
        return {"sent": False, "skipped": "disabled_by_user"}
    return send_login_notification(**context)


def queue_login_email(background_tasks, user: dict, request=None, mfa_used: bool = False) -> dict:
    """Queue the existing alert after successful authentication/session creation."""
    from .auth_otp import queue_login_notification

    context = _login_notification_context(user, request, mfa_used)
    if not context:
        return {"queued": False, "skipped": "not_eligible"}
    return queue_login_notification(background_tasks, **context)



def _parse_ts(value) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    return dt.datetime.fromisoformat(str(value))


def session_serialized(session: dict, current_session_id: str | None = None) -> dict:
    return {
        "session_id": session.get("session_id"),
        "device_label": session.get("device_label", ""),
        "ip_address": session.get("ip_address", ""),
        "created_at": session.get("created_at"),
        "last_seen_at": session.get("last_seen_at"),
        "expires_at": session.get("expires_at"),
        "current": bool(current_session_id and session.get("session_id") == current_session_id),
    }


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


def issue_session(store, user: dict, request, refresh_token: str | None = None) -> dict:
    """Create a persistent session and issue access + refresh tokens."""
    from .storage import datetime_now

    refresh = refresh_token or new_refresh_token()
    expires = (
        dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=settings.JWT_REFRESH_TTL_DAYS)
    ).isoformat()
    session = store.create_session(
        user["id"],
        hash_refresh_token(refresh),
        device_label_from_ua(request.headers.get("user-agent", "")),
        client_ip(request),
        expires,
    )
    session_id = session["session_id"]
    cache = get_session_cache()
    cache.set(
        session_id,
        {
            "session_id": session_id,
            "user_id": user["id"],
            "last_seen_at": datetime_now(),
            "expires_at": expires,
            "revoked": False,
        },
        _ttl_seconds(session),
    )
    access = create_access_token(user["id"], user.get("role", "user"), session_id)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "session_id": session_id,
        "expires_at": expires,
    }


def revoke_session(store, session_id: str, user_id: str | None = None, broadcast: bool = True) -> bool:
    """Revoke a session and drop it from the active cache."""
    store.revoke_session(session_id)
    try:
        get_session_cache().delete(session_id)
    except Exception:
        pass
    if broadcast and user_id:
        notify_user(user_id, "session_revoked", session_id=session_id)
    return True


def resolve_session(session_id: str, touch: bool = True):
    """Load + validate a session on every protected request.

    Verifies revocation, ``expires_at`` and inactivity (``last_seen_at`` +
    ``inactivity_timeout_minutes``). Returns ``(session, user, error_code)``.
    """
    if not session_id:
        return None, None, ERR_NOT_AUTHENTICATED
    store = get_auth_store()
    cache = get_session_cache()
    cached = cache.get(session_id)
    if cached:
        session = dict(cached)
    else:
        session = store.get_session(session_id)
        if not session:
            return None, None, ERR_SESSION_REVOKED
        if not session.get("revoked") and _parse_ts(session["expires_at"]) > dt.datetime.now(dt.timezone.utc):
            cache.set(
                session_id,
                {
                    "session_id": session_id,
                    "user_id": session.get("user_id"),
                    "last_seen_at": session.get("last_seen_at") or session.get("created_at"),
                    "expires_at": session.get("expires_at"),
                    "revoked": False,
                },
                _ttl_seconds(session),
            )
    if session.get("revoked"):
        cache.delete(session_id)
        return None, None, ERR_SESSION_REVOKED

    user = store.get_user(session.get("user_id"))
    if not user or not user.get("active", True):
        return None, None, ERR_SESSION_REVOKED

    if _parse_ts(session["expires_at"]) < dt.datetime.now(dt.timezone.utc):
        revoke_session(store, session_id, user["id"])
        return None, None, ERR_SESSION_EXPIRED

    timeout_minutes = normalize_user(user)["inactivity_timeout_minutes"]
    last_seen = _parse_ts(session.get("last_seen_at") or session.get("created_at"))
    if last_seen + dt.timedelta(minutes=timeout_minutes) < dt.datetime.now(dt.timezone.utc):
        revoke_session(store, session_id, user["id"])
        return None, None, ERR_SESSION_INACTIVE

    if touch:
        _touch_session_cache(cache, session, user)
    return session, user, None


_last_touch: dict[str, float] = {}


def _touch_session_cache(cache, session: dict, user: dict) -> None:
    """Refresh the cached ``last_seen_at`` at most every few seconds."""
    session_id = session["session_id"]
    now = time.monotonic()
    with threading.Lock():
        last = _last_touch.get(session_id, 0)
        if now - last < settings.SESSION_IDLE_TOUCH_SECONDS:
            return
        _last_touch[session_id] = now
    payload = dict(cache.get(session_id) or {})
    payload.update(
        {
            "last_seen_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "user_id": user["id"],
            "session_id": session_id,
            "revoked": False,
        }
    )
    cache.set(session_id, payload, _ttl_seconds(session))


def _ttl_seconds(session: dict) -> int:
    try:
        seconds = int(
            (_parse_ts(session["expires_at"]) - dt.datetime.now(dt.timezone.utc)).total_seconds()
        )
        return max(1, min(seconds, 60 * 24 * 3600))
    except Exception:
        return settings.JWT_REFRESH_TTL_DAYS * 24 * 3600
