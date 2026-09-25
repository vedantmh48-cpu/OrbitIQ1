"""Authentication & security helpers.

Password hashing uses PBKDF2-HMAC-SHA256 (stdlib) with per-user salts so no
binary bcrypt wheels are required. JWTs are signed with PyJWT using HS256.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings

_PBKDF2_ITERATIONS = 210_000


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return (
        f"pbkdf2_sha256${_PBKDF2_ITERATIONS}$"
        f"{base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_b64, digest_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------


def _issuer() -> str:
    return f"satquery-ai:{settings.APP_NAME}"


def create_access_token(
    user_id: str, role: str = "user", session_id: str | None = None
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "iss": _issuer(),
        "iat": now,
        "exp": now + timedelta(hours=settings.JWT_ACCESS_TTL_HOURS),
    }
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iss": _issuer(),
        "iat": now,
        "exp": now + timedelta(days=settings.JWT_REFRESH_TTL_DAYS),
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# Opaque session refresh tokens (v1 auth)
# ---------------------------------------------------------------------------


def new_refresh_token() -> str:
    """Unstructured high-entropy refresh token. Only its SHA-256 hash is
    persisted, so a leaked database can never be replayed to mint tokens."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_token(token: str, expected_type: str = "access") -> dict:
    """Decode+validate a token. Raises jwt.PyJWTError on any failure."""
    payload = jwt.decode(
        token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
    )
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("Unexpected token type")
    return payload


# ---------------------------------------------------------------------------
# One-time reset tokens
# ---------------------------------------------------------------------------


def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()