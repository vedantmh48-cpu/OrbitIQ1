"""Shared FastAPI dependencies: current user, current session, admin, etc."""
from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .auth_runtime import (
    ERR_SESSION_EXPIRED,
    ERR_SESSION_INACTIVE,
    ERR_SESSION_REVOKED,
    resolve_session,
)
from .auth_store import normalize_user
from .errors import app_error
from .security import decode_token
from .storage import get_db

_bearer = HTTPBearer(auto_error=False)

_SESSION_ERROR_DETAILS = {
    ERR_SESSION_REVOKED: ("Your session was signed out on another device.", "SESSION_REVOKED"),
    ERR_SESSION_EXPIRED: ("Your session has expired. Please sign in again.", "SESSION_EXPIRED"),
    ERR_SESSION_INACTIVE: (
        "You were signed out due to inactivity. Please sign in again.",
        "SESSION_INACTIVE",
    ),
}


def _session_http_error(code: str) -> HTTPException:
    detail, _ = _SESSION_ERROR_DETAILS.get(
        code, ("Your session is no longer valid. Please sign in again.", code)
    )
    return app_error(status.HTTP_401_UNAUTHORIZED, detail, code=code)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(_bearer)):
    if credentials is None:
        raise app_error(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated. Please sign in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except jwt.PyJWTError:
        raise app_error(
            status.HTTP_401_UNAUTHORIZED,
            "Your session has expired. Please sign in again.",
            code="TOKEN_INVALID",
        )
    # V1 sessions carry a session-id claim -> validate via the auth store +
    # session cache (enforces expires_at / last_seen_at on every request).
    if payload.get("sid"):
        _, user, error = resolve_session(payload["sid"], touch=True)
        if error:
            raise _session_http_error(error)
        return user

    db = get_db()
    user = db.find_one("users", {"id": payload.get("sub")})
    if not user:
        raise HTTPException(status_code=401, detail="Account no longer exists.")
    if not user.get("active", True):
        raise HTTPException(status_code=403, detail="Account has been deactivated.")
    return normalize_user(user)


def get_current_session(user: dict = Depends(get_current_user), credentials: HTTPAuthorizationCredentials = Depends(_bearer)):
    """Resolve the session record behind the current access token."""
    if credentials is None:
        raise app_error(status.HTTP_401_UNAUTHORIZED, "Not authenticated.")
    payload = decode_token(credentials.credentials, expected_type="access")
    session_id = payload.get("sid")
    if not session_id:
        raise app_error(status.HTTP_401_UNAUTHORIZED, "Session context not found.", code="TOKEN_INVALID")
    session, _, error = resolve_session(session_id, touch=True)
    if error:
        raise _session_http_error(error)
    return session


def require_admin(user: dict = Depends(get_current_user)):
    if user.get("role") not in ("admin",):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required.",
        )
    return user


def require_analyst(user: dict = Depends(get_current_user)):
    if user.get("role") not in ("admin", "analyst"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Analyst or admin privileges required.",
        )
    return user