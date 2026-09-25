"""TOTP (RFC 6238) implementation with no third-party dependencies.

Used for MFA enablement / challenge. Secrets are Base32-encoded; the
standard ``otpauth://`` URI is emitted so any authenticator app can enrol.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time

TOTP_STEP_SECONDS = 30
TOTP_DIGITS = 6
TOTP_WINDOW = 1


def generate_secret() -> str:
    """Return a Base32 (no padding) secret for authenticator enrolment."""
    raw = secrets.token_bytes(20)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _totp_at(secret_b32: str, counter: int) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 15
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 10 ** TOTP_DIGITS
    return f"{code:0{TOTP_DIGITS}d}"


def current_code(secret_b32: str) -> str:
    return _totp_at(secret_b32, int(time.time() // TOTP_STEP_SECONDS))


def validate_code(secret_b32: str, code: str, window: int = TOTP_WINDOW) -> bool:
    if not secret_b32 or not code:
        return False
    code = code.strip()
    if not code.isdigit() or len(code) != TOTP_DIGITS:
        return False
    current = int(time.time() // TOTP_STEP_SECONDS)
    for step in range(current - window, current + window + 1):
        if hmac.compare_digest(_totp_at(secret_b32, step), code):
            return True
    return False


def otpauth_uri(secret_b32: str, account_name: str, issuer: str = "SatQuery AI") -> str:
    import urllib.parse

    label = urllib.parse.quote(f"{issuer}:{account_name}")
    params = urllib.parse.urlencode(
        {
            "secret": secret_b32,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": TOTP_DIGITS,
            "period": TOTP_STEP_SECONDS,
        }
    )
    return f"otpauth://totp/{label}?{params}"
