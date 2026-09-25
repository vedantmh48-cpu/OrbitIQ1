"""One-time password (OTP) generation, hashing and delivery.

Codes are 6 digits, stored as SHA-256 hashes only, and are short-lived.

Delivery goes through :mod:`app.services.mailer` (Gmail SMTP by default, see
``.env.example``). When SMTP is not configured - or when a send fails - the
code is written to the server log and returned to the caller as ``demo_code``
so the full flow keeps working locally without a mail server.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks

from .config import settings
from .middleware import logger
from .services import mailer

IST = ZoneInfo("Asia/Kolkata")


def generate_otp() -> str:
    """Return a 6-digit numeric OTP (zero-padded)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(code: str) -> str:
    return hashlib.sha256(f"otp:{settings.JWT_SECRET}:{code}".encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def _demo_fallback(to_email: str, purpose: str, code: str, reason: str) -> dict:
    """Return the code only to the local/demo caller without logging it."""
    logger.info(
        "[OTP][%s] not e-mailed to %s (%s); demo_code returned to the caller",
        purpose,
        mailer.mask_email(to_email),
        reason,
    )
    return {"delivered": False, "demo_code": code, "error": reason}


def send_otp(to_email: str, purpose: str, code: str, name: str | None = None) -> dict:
    """E-mail a 6-digit OTP via the configured SMTP relay.

    Returns a response fragment the caller merges in. When the code could not
    be e-mailed it contains ``demo_code`` (development fallback) plus the
    reason, and the caller's existing behaviour is preserved.
    """
    result = mailer.send_template(
        "otp",
        to_email,
        label=f"otp:{purpose}",
        code=code,
        purpose=purpose,
        name=name or "",
        ttl_minutes=settings.AUTH_OTP_TTL_MINUTES,
    )
    if not result.get("sent"):
        return _demo_fallback(
            to_email, purpose, code, result.get("error") or "delivery_failed"
        )
    logger.info("[OTP][%s] sent to %s", purpose, mailer.mask_email(to_email))
    return {"delivered": True}


def queue_otp(
    background_tasks: BackgroundTasks,
    to_email: str,
    purpose: str,
    code: str,
    name: str | None = None,
) -> dict:
    """Queue configured SMTP delivery without changing OTP creation or expiry.

    The disabled-mail development fallback remains synchronous because callers
    need its ``demo_code`` in their existing response. With configured SMTP,
    the exact already-generated code is sent once after the response.
    """
    if not mailer.is_configured():
        return send_otp(to_email, purpose, code, name)
    background_tasks.add_task(send_otp, to_email, purpose, code, name)
    return {"queued": True}


def send_login_notification(
    to_email: str,
    name: str | None = None,
    device_label: str = "",
    ip_address: str = "",
    when: str = "",
    mfa_used: bool = False,
) -> dict:
    """E-mail a "new sign-in" security alert. Never raises."""
    if not when:
        when = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    return mailer.send_template(
        "login_notification",
        to_email,
        label="login_notification",
        name=name or "",
        email=to_email,
        when=when,
        device_label=device_label,
        ip_address=ip_address,
        mfa_used=bool(mfa_used),
    )


def queue_login_notification(
    background_tasks: BackgroundTasks,
    to_email: str,
    name: str | None = None,
    device_label: str = "",
    ip_address: str = "",
    when: str = "",
    mfa_used: bool = False,
) -> dict:
    """Queue one existing login alert; delivery failure remains non-fatal."""
    background_tasks.add_task(
        send_login_notification,
        to_email,
        name,
        device_label,
        ip_address,
        when,
        mfa_used,
    )
    return {"queued": True}


def send_password_reset(to_email: str, reset_url: str, name: str | None = None) -> dict:
    """E-mail a password-reset link (used by the legacy reset flow)."""
    return mailer.send_template(
        "password_reset",
        to_email,
        label="password_reset",
        name=name or "",
        reset_url=reset_url,
        ttl_minutes=settings.PASSWORD_RESET_TTL_MINUTES,
    )


def queue_password_reset(
    background_tasks: BackgroundTasks, to_email: str, reset_url: str, name: str | None = None
) -> dict:
    """Queue delivery of an already-created reset link exactly once."""
    background_tasks.add_task(send_password_reset, to_email, reset_url, name)
    return {"queued": True}


def mail_status() -> dict:
    """Secret-free mail configuration snapshot (host, masked user, mode)."""
    return mailer.status()
