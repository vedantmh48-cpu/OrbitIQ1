"""OrbitIQ e-mail delivery over SMTP (Gmail-ready).

The default transport is **Gmail** (``smtp.gmail.com:587`` with STARTTLS) but
any standards-compliant SMTP relay works. Every credential is read from the
environment (see ``.env.example``) - nothing is hard-coded and the app password
is never logged, returned by an API, or echoed in an error message.

Design
------
* **Transport**: :func:`send_email` builds the message, :func:`_deliver` opens
  the connection (STARTTLS / implicit SSL / plaintext), authenticates and
  sends. ``_deliver`` is deliberately separate so tests can stub the network
  without touching the authentication flow.
* **Templates**: :func:`register_template` + :func:`render_template` give a
  small registry. Each transactional template supplies both plain-text and
  HTML parts; the transport sends them as ``multipart/alternative`` without
  requiring call-site changes.
* **Never fatal**: delivery is best-effort. ``send_email`` returns a result
  dict (``sent`` / ``error``) instead of raising, so registration, login and
  MFA flows keep working when Gmail is unreachable; callers keep their existing
  ``demo_code`` fallback in that case.
"""
from __future__ import annotations

import smtplib
import ssl
import time
from email.message import EmailMessage
from html import escape
from typing import Callable
from zoneinfo import ZoneInfo

from ..config import settings
from ..middleware import logger

PRODUCT_NAME = "OrbitIQ"
IST = ZoneInfo("Asia/Kolkata")

_TEMPLATES: dict[str, Callable[[dict], dict]] = {}


# ---------------------------------------------------------------------------
# Configuration helpers (secret-free)
# ---------------------------------------------------------------------------


def is_configured() -> bool:
    """True when host + mailbox + app password are present and mail is on."""
    return settings.mail_enabled()


def provider_name() -> str:
    """Human label for the configured relay (``gmail`` by default)."""
    host = (settings.SMTP_HOST or "").lower()
    if host.endswith("gmail.com"):
        return "gmail"
    return host or "none"


def transport_label() -> str:
    if settings.SMTP_USE_SSL:
        return "ssl"
    if settings.SMTP_USE_STARTTLS:
        return "starttls"
    return "plaintext"


def mask_email(address: str | None) -> str:
    """Keep the domain, mask the local part: ``ab***@example.com``."""
    value = (address or "").strip()
    if not value:
        return ""
    local, _, domain = value.partition("@")
    if not domain:
        return "***"
    return f"{local[:1]}{'*' * max(len(local) - 1, 0)}@{domain}"


def status() -> dict:
    """Secret-free snapshot of the mail configuration (admin diagnostics)."""
    return {
        "product": PRODUCT_NAME,
        "enabled": is_configured(),
        "mode": settings.MAIL_MODE,
        "provider": provider_name(),
        "transport": transport_label(),
        "host": settings.SMTP_HOST,
        "port": settings.SMTP_PORT,
        "username": mask_email(settings.SMTP_USERNAME),
        "from": settings.SMTP_FROM,
        "from_name": settings.SMTP_FROM_NAME,
        "reply_to": settings.SMTP_REPLY_TO,
        "credentials_present": settings.mail_credentials_present(),
        "login_notifications": settings.LOGIN_NOTIFICATION_ENABLED,
        "templates": available_templates(),
    }


def _redact(text: object) -> str:
    """Replace the app password with ``***`` in any message that leaves here."""
    out = str(text)
    secret = settings.SMTP_PASSWORD
    if secret and len(secret) >= 4:
        out = out.replace(secret, "***")
    return out


# ---------------------------------------------------------------------------
# Message building & transport
# ---------------------------------------------------------------------------


def _build_message(
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
    reply_to: str | None = None,
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.sender_header()
    message["To"] = to_email
    reply = reply_to or settings.SMTP_REPLY_TO
    if reply:
        message["Reply-To"] = reply
    message.set_content(text_body)
    if html_body:
        # HTML-ready: becomes multipart/alternative with the text fallback.
        message.add_alternative(html_body, subtype="html")
    return message


def _deliver(message: EmailMessage) -> None:
    """Open a connection, authenticate and send. Raises on any failure."""
    context = ssl.create_default_context()
    timeout = settings.SMTP_TIMEOUT_SECONDS
    if settings.SMTP_USE_SSL:
        with smtplib.SMTP_SSL(
            settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout, context=context
        ) as server:
            if settings.SMTP_USERNAME:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(message)
        return
    with smtplib.SMTP(
        settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout
    ) as server:
        server.ehlo()
        if settings.SMTP_USE_STARTTLS:
            server.starttls(context=context)
            server.ehlo()
        if settings.SMTP_USERNAME:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(message)


def _is_transient_delivery_error(exc: Exception) -> bool:
    """Only retry connection-level failures, never bad credentials or recipients."""
    return isinstance(
        exc,
        (OSError, smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected),
    )


def send_email(
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
    reply_to: str | None = None,
    label: str = "email",
) -> dict:
    """Send one e-mail. Never raises - inspect ``sent`` / ``error``.

    Returns ``sent`` (bool), ``delivered`` (alias of ``sent``), ``error``
    (redacted string or ``None``), ``provider``, ``transport`` and a masked
    ``recipient``. The app password never appears in the result.
    """
    result = {
        "sent": False,
        "delivered": False,
        "error": None,
        "provider": provider_name(),
        "transport": transport_label(),
        "recipient": mask_email(to_email),
    }
    if not to_email or "@" not in str(to_email):
        result["error"] = "invalid_recipient"
        logger.warning("[MAIL] %s skipped: invalid recipient address", label)
        return result
    if not is_configured():
        result["error"] = "mail_disabled"
        logger.info("[MAIL] %s not sent (mail disabled)", label)
        return result

    message = _build_message(to_email, subject, text_body, html_body, reply_to)
    try:
        _deliver(message)
    except Exception as exc:  # pragma: no cover - depends on the SMTP server
        # Gmail can occasionally close a STARTTLS connection mid-handshake
        # (for example SSLEOFError). Retry once only; _deliver creates a new
        # SMTP object each time, so no broken connection is ever reused.
        if _is_transient_delivery_error(exc):
            logger.warning(
                "[MAIL] %s transient delivery failure for %s; retrying once (%s)",
                label,
                result["recipient"],
                _redact(f"{type(exc).__name__}: {exc}"),
            )
            try:
                time.sleep(0.25)
                _deliver(message)
            except Exception as retry_exc:
                exc = retry_exc
            else:
                result["sent"] = True
                result["delivered"] = True
                logger.info(
                    "[MAIL] %s sent to %s via %s (%s; retry)",
                    label,
                    result["recipient"],
                    provider_name(),
                    transport_label(),
                )
                return result
        result["error"] = _redact(f"{type(exc).__name__}: {exc}")
        logger.warning(
            "[MAIL] %s delivery failed for %s via %s:%s (%s)",
            label,
            result["recipient"],
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            result["error"],
        )
        return result

    result["sent"] = True
    result["delivered"] = True
    logger.info(
        "[MAIL] %s sent to %s via %s (%s)",
        label,
        result["recipient"],
        provider_name(),
        transport_label(),
    )
    return result


def check_connection() -> dict:
    """Probe the SMTP server without authenticating (admin diagnostics)."""
    result = {
        "ok": False,
        "provider": provider_name(),
        "host": settings.SMTP_HOST,
        "port": settings.SMTP_PORT,
        "transport": transport_label(),
        "starttls_supported": False,
        "server": "",
        "error": None,
    }
    timeout = settings.SMTP_TIMEOUT_SECONDS
    try:
        context = ssl.create_default_context()
        if settings.SMTP_USE_SSL:
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout, context=context
            )
        else:
            server = smtplib.SMTP(
                settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout
            )
        try:
            code, banner = server.ehlo()
            result["server"] = (
                banner.decode("utf-8", "replace")
                if isinstance(banner, bytes)
                else str(banner)
            )
            result["starttls_supported"] = "starttls" in (server.esmtp_features or {})
            if settings.SMTP_USE_STARTTLS and not settings.SMTP_USE_SSL:
                server.starttls(context=context)
                server.ehlo()
            result["ok"] = code in (220, 250)
        finally:
            try:
                server.quit()
            except Exception:  # pragma: no cover - best effort cleanup
                pass
    except Exception as exc:
        result["error"] = _redact(f"{type(exc).__name__}: {exc}")
        logger.warning(
            "[MAIL] connection check failed for %s:%s (%s)",
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            result["error"],
        )
    return result


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def register_template(name: str):
    """Decorator registering a template builder ``ctx -> {subject, text, html?}``."""

    def decorator(builder: Callable[[dict], dict]):
        _TEMPLATES[name] = builder
        return builder

    return decorator


def available_templates() -> list[str]:
    return sorted(_TEMPLATES)


def render_template(template: str, **context) -> dict:
    """Render a template to ``{"subject", "text", "html"}`` (no I/O)."""
    builder = _TEMPLATES.get(template)
    if builder is None:
        raise KeyError(f"Unknown e-mail template: {template}")
    rendered = dict(builder(dict(context)))
    rendered.setdefault("subject", f"[{PRODUCT_NAME}] Notification")
    rendered.setdefault("text", "")
    rendered.setdefault("html", None)
    return rendered


def send_template(template: str, to_email: str, label: str | None = None, **context) -> dict:
    """Render + send a template in one step."""
    rendered = render_template(template, **context)
    return send_email(
        to_email,
        rendered["subject"],
        rendered["text"],
        rendered.get("html"),
        label=label or template,
    )


def _greeting(name: str | None) -> str:
    """Return a friendly, consistent greeting without trusting input HTML."""
    cleaned = (name or "").strip()
    return f"Hello {cleaned or 'there'},"


def _footer_text(team: str = "OrbitIQ Team") -> str:
    return (
        f"Regards,\n{team}\n\n"
        f"---\n{PRODUCT_NAME}\nSatellite intelligence platform\n"
        "This is an automated email. Please do not reply."
    )


def _html_brand() -> str:
    """Text-only brand header; transactional messages intentionally omit a logo."""
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0">'
        '<tr><td style="vertical-align:middle;">'
        '<div style="font-family:Arial,sans-serif;font-size:21px;line-height:24px;'
        'font-weight:700;letter-spacing:-0.3px;color:#0f172a;">OrbitIQ</div>'
        '<div style="font-family:Arial,sans-serif;font-size:10px;line-height:15px;'
        'letter-spacing:1px;text-transform:uppercase;color:#64748b;">'
        'Satellite intelligence</div></td></tr></table>'
    )


def _detail_rows(rows: list[tuple[str, str]]) -> str:
    rendered = []
    for label, value in rows:
        clean = str(value or "").strip()
        if clean:
            rendered.append(
                '<tr><td style="padding:7px 0;color:#64748b;font-size:14px;'
                'line-height:20px;width:42%;">'
                f'{escape(label)}</td><td style="padding:7px 0;color:#0f172a;'
                'font-size:14px;line-height:20px;font-weight:600;">'
                f'{escape(clean)}</td></tr>'
            )
    if not rendered:
        return ""
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'border="0" style="border-collapse:collapse;">' + "".join(rendered) + "</table>"
    )


def _email_html(
    label: str,
    heading: str,
    intro: str,
    body: str,
    *,
    security_note: str = "",
    team: str = "OrbitIQ Team",
) -> str:
    """Shared, table-based transactional-email shell with safe escaped content."""
    note = (
        '<div style="margin-top:24px;padding:14px 16px;border:1px solid #cbd5e1;'
        'border-radius:8px;background:#f8fafc;font-family:Arial,sans-serif;'
        'font-size:13px;line-height:20px;color:#334155;">'
        f'{security_note}</div>'
        if security_note
        else ""
    )
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f1f5f9;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f1f5f9;"><tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;background:#ffffff;border:1px solid #dbe3ee;border-radius:12px;overflow:hidden;">
<tr><td style="padding:30px 32px 20px;">{_html_brand()}</td></tr>
<tr><td style="padding:0 32px 32px;font-family:Arial,sans-serif;color:#0f172a;">
<div style="font-size:11px;line-height:16px;font-weight:700;letter-spacing:1.1px;text-transform:uppercase;color:#0284c7;">{escape(label)}</div>
<h1 style="margin:10px 0 12px;font-size:27px;line-height:34px;letter-spacing:-0.4px;font-weight:700;color:#0f172a;">{escape(heading)}</h1>
<p style="margin:0;font-size:16px;line-height:25px;color:#334155;">{escape(intro)}</p>
{body}{note}
<p style="margin:25px 0 0;font-size:14px;line-height:21px;color:#334155;">Regards,<br>{escape(team)}</p>
</td></tr>
<tr><td style="padding:20px 32px;background:#f8fafc;border-top:1px solid #dbe3ee;font-family:Arial,sans-serif;font-size:12px;line-height:18px;color:#64748b;">
<strong style="color:#334155;">OrbitIQ</strong><br>Satellite intelligence platform<br>This is an automated email. Please do not reply.
</td></tr></table></td></tr></table></body></html>'''


def _ist_now_stamp() -> str:
    """``2026-09-22 20:15:00 IST`` - used in transactional e-mail bodies."""
    import datetime

    return datetime.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")


_OTP_ACTIONS = {
    "register": "Use this code to confirm your OrbitIQ account:",
    "password_change": "Use this code to confirm your password change:",
    "reset_password": "Use this code to reset your OrbitIQ password:",
}




@register_template("login_notification")
def _login_notification_template(ctx: dict) -> dict:
    when = str(ctx.get("when") or "").strip()
    device = str(ctx.get("device_label") or "").strip()
    ip_address = str(ctx.get("ip_address") or "").strip()
    rows = [("Date & time", when), ("IP address", ip_address), ("Device", device)]
    plain_rows = "\n".join(f"{label}: {value}" for label, value in rows if value)
    text = (
        f"{_greeting(ctx.get('name'))}\n\n"
        f"Your {PRODUCT_NAME} account was successfully signed in.\n\n"
        f"Sign-in details:\n{plain_rows}\n\n"
        f"If this was you, no action is needed.\n\n"
        "If you do not recognize this sign-in, secure your account immediately by "
        "changing your password and reviewing your active sessions.\n\n"
        f"{_footer_text('OrbitIQ Security Team')}\n"
    )
    return {
        "subject": "New sign-in to your OrbitIQ account",
        "text": text,
        "html": _email_html(
            "Security alert", "A successful sign-in was detected.",
            "Your OrbitIQ account was successfully signed in.",
            '<div style="margin-top:24px;padding:18px;border:1px solid #dbe3ee;border-radius:8px;background:#ffffff;">'
            '<div style="font-size:13px;font-weight:700;color:#475569;margin-bottom:8px;">SIGN-IN DETAILS</div>'
            f'{_detail_rows(rows)}</div>',
            security_note="If you do not recognize this sign-in, change your password and review your active sessions immediately.",
            team="OrbitIQ Security Team",
        ),
    }


@register_template("password_reset")
def _password_reset_template(ctx: dict) -> dict:
    ttl = int(ctx.get("ttl_minutes") or settings.PASSWORD_RESET_TTL_MINUTES)
    url = str(ctx.get("reset_url") or settings.APP_PUBLIC_URL)
    text = (
        f"{_greeting(ctx.get('name'))}\n\n"
        f"We received a request to reset the password for your {PRODUCT_NAME} account.\n\n"
        "Reset Password\n"
        f"{url}\n\n"
        f"This link expires in {ttl} minutes. If you did not request a password reset, "
        "you can safely ignore this email. Your password will remain unchanged.\n\n"
        "For your security, never share this reset link with anyone.\n\n"
        f"{_footer_text('OrbitIQ Security Team')}\n"
    )
    return {
        "subject": "Reset your OrbitIQ password",
        "text": text,
        "html": _email_html(
            "Password reset", "Reset your OrbitIQ password",
            "We received a request to reset the password for your OrbitIQ account.",
            '<div style="margin-top:24px;text-align:center;">'
            f'<a href="{escape(url, quote=True)}" style="display:inline-block;padding:14px 24px;background:#0284c7;color:#ffffff;text-decoration:none;border-radius:7px;font-size:16px;font-weight:700;">Reset Password</a>'
            '</div><p style="margin:20px 0 0;font-size:13px;line-height:20px;color:#475569;">'
            'If the button does not work, copy and paste this link into your browser:<br>'
            f'<a href="{escape(url, quote=True)}" style="color:#0369a1;word-break:break-all;">{escape(url)}</a></p>'
            f'<p style="margin:16px 0 0;font-size:14px;line-height:21px;color:#334155;">This link expires in {ttl} minutes.</p>',
            security_note="If you did not request a password reset, you can safely ignore this email. Your password will remain unchanged. Never share this reset link.",
            team="OrbitIQ Security Team",
        ),
    }


@register_template("smtp_test")
def _smtp_test_template(ctx: dict) -> dict:
    when = str(ctx.get("when") or _ist_now_stamp())
    text = (
        f"{_greeting(ctx.get('name'))}\n\n"
        f"{PRODUCT_NAME} email delivery is working correctly.\n\n"
        "This is a test message generated by the OrbitIQ system.\n\n"
        "Delivery details:\n"
        f"Environment: {settings.ENVIRONMENT}\nTimestamp: {when}\nMail provider: {provider_name()}\n\n"
        f"No action is required.\n\n{_footer_text('OrbitIQ System')}\n"
    )
    return {
        "subject": "OrbitIQ email delivery test",
        "text": text,
        "html": _email_html(
            "System test", "Email delivery is working correctly.",
            "This is a test message generated by the OrbitIQ system.",
            '<div style="margin-top:24px;padding:18px;border:1px solid #dbe3ee;border-radius:8px;background:#ffffff;">'
            '<div style="font-size:13px;font-weight:700;color:#475569;margin-bottom:8px;">DELIVERY DETAILS</div>'
            f'{_detail_rows([("Environment", settings.ENVIRONMENT), ("Timestamp", when), ("Mail provider", provider_name())])}</div>',
            team="OrbitIQ System",
        ),
    }

@register_template("otp")
def _otp_template(ctx: dict) -> dict:
    code = str(ctx.get("code", ""))
    purpose = str(ctx.get("purpose") or "register")
    ttl = int(ctx.get("ttl_minutes") or settings.AUTH_OTP_TTL_MINUTES)
    action = _OTP_ACTIONS.get(purpose, "Use this code to verify your identity:")
    text = (
        f"{_greeting(ctx.get('name'))}\n\n"
        f"Welcome to {PRODUCT_NAME}.\n\n{action}\n\n"
        f"Verification code: {code}\n\n"
        f"This code expires in {ttl} minutes.\n\n"
        "For your security, never share this verification code with anyone.\n\n"
        f"If you did not request this code, you can safely ignore this email.\n\n{_footer_text()}\n"
    )
    return {
        "subject": "Verify your OrbitIQ account",
        "text": text,
        "html": _email_html(
            "Email verification", "Verify your OrbitIQ account",
            f"Welcome to {PRODUCT_NAME}. {action}",
            '<div style="margin-top:24px;padding:22px;border:1px solid #bae6fd;border-radius:10px;background:#f0f9ff;text-align:center;">'
            '<div style="font-size:12px;line-height:18px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#0369a1;">Verification code</div>'
            f'<div style="margin-top:10px;font-family:Arial,sans-serif;font-size:32px;line-height:38px;font-weight:700;letter-spacing:8px;color:#0f172a;">{escape(code)}</div>'
            f'<div style="margin-top:12px;font-size:13px;line-height:20px;color:#475569;">Expires in {ttl} minutes</div></div>',
            security_note="For your security, never share this verification code with anyone. If you did not create an OrbitIQ account, you can safely ignore this email.",
        ),
    }
