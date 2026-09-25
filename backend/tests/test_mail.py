"""E-mail delivery tests: Gmail SMTP transport, OTP e-mails, login alerts.

``app.services.mailer._deliver`` (the only network-facing call) is stubbed so
the suite never opens a real connection, while everything above it -
configuration, templates, the OTP and login-notification flows, the admin
diagnostics - runs for real.
"""
import json
import re
import smtplib
import socket
import ssl
import threading

import pytest
from fastapi import BackgroundTasks

from app.auth_otp import queue_otp
from app.auth_totp import current_code
from app.config import normalize_app_password
from app.middleware import redact_sensitive_log_text
from app.services import mailer

GMAIL_USER = "orbitiq.tester@gmail.com"
APP_PASSWORD = "abcdefghijklmnop"  # the normalised form of "abcd efgh ijkl mnop"
MASKED_GMAIL_USER = "o*************@gmail.com"  # "orbitiq.tester" masked
STUDENT_EMAIL = "mia.mail@orbitiq.ai"


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def outbox(monkeypatch):
    """Configure Gmail SMTP and capture messages instead of sending them."""
    sent: list = []
    for key, value in {
        "MAIL_MODE": "auto",
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_PORT": 587,
        "SMTP_USERNAME": GMAIL_USER,
        "SMTP_PASSWORD": APP_PASSWORD,
        "SMTP_FROM": GMAIL_USER,
        "SMTP_FROM_NAME": "OrbitIQ",
        "SMTP_USE_STARTTLS": True,
        "SMTP_USE_SSL": False,
        "SMTP_TIMEOUT_SECONDS": 15,
        "LOGIN_NOTIFICATION_ENABLED": True,
        "APP_PUBLIC_URL": "http://localhost:5173",
    }.items():
        monkeypatch.setattr(f"app.config.settings.{key}", value, raising=False)
    monkeypatch.setattr(mailer, "_deliver", sent.append)
    return sent


def _register_student(client, email=STUDENT_EMAIL, password="Password1"):
    return client.post(
        "/api/v1/auth/register",
        json={
            "account_type": "student",
            "full_name": "Mia Mail",
            "email": email,
            "password": password,
            "confirm_password": password,
            "institution": "OrbitIQ University",
            "course": "Remote Sensing",
            "year_of_study": 2,
        },
    )


def _register_gov_org(client, email="gwen.gov@state.gov"):
    return client.post(
        "/api/v1/auth/register",
        json={
            "account_type": "organization",
            "org_name": "State Defense Bureau",
            "org_type": "defense",
            "official_domain": "state.gov",
            "admin_name": "Gwen Gov",
            "admin_email": email,
            "team_size": 40,
            "intended_use": "National emergency response mapping.",
            "password": "Password1",
            "confirm_password": "Password1",
        },
    )


def _plain_body(message) -> str:
    if message.is_multipart():
        part = message.get_body(preferencelist=("plain",))
        return part.get_content() if part else ""
    return message.get_content()


def _six_digit_code(message) -> str:
    match = re.search(r"\b(\d{6})\b", _plain_body(message))
    assert match, "no 6-digit code found in the e-mail body"
    return match.group(1)


def _verify_with_email_code(client, outbox, email):
    code = _six_digit_code(outbox[-1])
    return client.post("/api/v1/auth/verify-email", json={"email": email, "code": code})


# ---------------------------------------------------------------------------
# Configuration & secrecy
# ---------------------------------------------------------------------------


def test_app_password_spaces_are_stripped():
    assert normalize_app_password("abcd efgh ijkl mnop") == APP_PASSWORD
    assert normalize_app_password("") == ""


def test_all_transactional_templates_have_safe_html_and_text(outbox):
    """Template rendering is local-only; the delivery function remains stubbed."""
    cases = {
        "otp": {"code": "123456", "purpose": "register", "name": ""},
        "login_notification": {
            "name": "",
            "when": "",
            "device_label": "",
            "ip_address": "",
        },
        "password_reset": {"name": "", "reset_url": "https://example.test/reset"},
        "smtp_test": {"name": "", "email": "admin@example.test"},
    }
    for name, context in cases.items():
        rendered = mailer.render_template(name, **context)
        assert rendered["text"]
        assert rendered["html"]
        assert "OrbitIQ" in rendered["html"]
        assert "cid:orbitiq-logo" not in rendered["html"]


def test_status_masks_credentials_and_never_leaks_the_password(outbox):
    status = mailer.status()
    assert status["enabled"] is True
    assert status["provider"] == "gmail"
    assert status["transport"] == "starttls"
    assert status["host"] == "smtp.gmail.com"
    assert status["port"] == 587
    assert status["from_name"] == "OrbitIQ"
    assert status["username"] == MASKED_GMAIL_USER

    payload = json.dumps(status)
    assert APP_PASSWORD not in payload
    assert status["username"] != GMAIL_USER  # masked, never the raw mailbox
    assert status["credentials_present"] is True
    assert "smtp_password" not in payload.lower()


def test_mail_disabled_keeps_the_demo_code_fallback(client, monkeypatch):
    monkeypatch.setattr("app.config.settings.MAIL_MODE", "false", raising=False)
    monkeypatch.setattr("app.config.settings.SMTP_USERNAME", "", raising=False)
    monkeypatch.setattr("app.config.settings.SMTP_PASSWORD", "", raising=False)
    assert mailer.is_configured() is False

    body = _register_student(client, email="offline.user@orbitiq.ai").json()
    assert len(body["demo_code"]) == 6


# ---------------------------------------------------------------------------
# 1. Registration -> OTP e-mail
# ---------------------------------------------------------------------------


def test_registration_sends_the_otp_email(client, outbox):
    response = _register_student(client)
    assert response.status_code == 201, response.text
    body = response.json()

    # Real delivery: the code is no longer echoed in the API response.
    assert "demo_code" not in body
    assert body["requires_email_verification"] is True

    assert len(outbox) == 1
    message = outbox[0]
    assert message["To"] == STUDENT_EMAIL
    assert message["From"] == f"OrbitIQ <{GMAIL_USER}>"
    assert message["Subject"] == "Verify your OrbitIQ account"

    text = _plain_body(message)
    assert "Hello Mia Mail," in text
    assert "confirm your OrbitIQ account" in text
    assert "Regards,\nOrbitIQ Team" in text
    code = _six_digit_code(message)
    assert code in text
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "OrbitIQ" in html
    assert "cid:orbitiq-logo" not in html
    assert not any(part["Content-ID"] == "<orbitiq-logo>" for part in message.walk())
    assert "Verification code" in html
    assert APP_PASSWORD not in text
    assert APP_PASSWORD not in json.dumps(body)


def test_invalid_recipient_is_reported_and_not_sent(outbox):
    result = mailer.send_email("not-an-address", "subject", "body", label="unit")
    assert result["sent"] is False
    assert result["error"] == "invalid_recipient"
    assert outbox == []



def test_otp_verification_uses_the_emailed_code(client, outbox):
    _register_student(client)
    response = _verify_with_email_code(client, outbox, STUDENT_EMAIL)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["user"]["email_verified"] is True
    assert data["access_token"] and data["refresh_token"] and data["session_id"]
    # Verification issues an authenticated session, so it also produces the
    # new-sign-in security alert.
    assert len(outbox) == 2
    assert outbox[1]["Subject"] == "New sign-in to your OrbitIQ account"


# ---------------------------------------------------------------------------
# 2. Resending the verification OTP
# ---------------------------------------------------------------------------


def test_otp_resend_sends_a_fresh_code(client, outbox):
    _register_student(client, email="resend@orbitiq.ai")
    first_code = _six_digit_code(outbox[0])

    response = client.post(
        "/api/v1/auth/verify-email/resend", json={"email": "resend@orbitiq.ai"}
    )
    assert response.status_code == 200
    assert "demo_code" not in response.json()
    assert len(outbox) == 2
    assert outbox[1]["To"] == "resend@orbitiq.ai"

    second_code = _six_digit_code(outbox[1])
    assert second_code != first_code

    verify = client.post(
        "/api/v1/auth/verify-email",
        json={"email": "resend@orbitiq.ai", "code": second_code},
    )
    assert verify.status_code == 200
    assert verify.json()["user"]["email_verified"] is True


def test_password_change_otp_uses_the_same_mailer(client, outbox):
    _register_student(client, email="pwd@orbitiq.ai")
    data = _verify_with_email_code(client, outbox, "pwd@orbitiq.ai").json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    response = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={
            "current_password": "Password1",
            "new_password": "FreshPass9",
            "confirm_password": "FreshPass9",
        },
    )
    assert response.status_code == 200
    assert "demo_code" not in response.json()
    assert len(outbox) == 3
    assert "confirm your password change" in _plain_body(outbox[2])



# ---------------------------------------------------------------------------
# 3. Successful login -> "new sign-in" notification
# ---------------------------------------------------------------------------


def test_login_sends_the_notification_email(client, outbox):
    _register_student(client, email="notify@orbitiq.ai")
    _verify_with_email_code(client, outbox, "notify@orbitiq.ai")
    outbox.clear()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "notify@orbitiq.ai", "password": "Password1"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["access_token"]

    assert len(outbox) == 1
    message = outbox[0]
    assert message["To"] == "notify@orbitiq.ai"
    assert message["Subject"] == "New sign-in to your OrbitIQ account"
    text = _plain_body(message)
    assert "Your OrbitIQ account was successfully signed in." in text
    assert "Date & time:" in text
    assert "IP address:" in text
    assert "Device: Browser" in text  # from the test client's user agent
    assert "If you do not recognize this sign-in" in text
    assert APP_PASSWORD not in text


def test_mfa_login_sends_the_notification_email(client, outbox):
    _register_gov_org(client)
    verified = _verify_with_email_code(client, outbox, "gwen.gov@state.gov").json()
    headers = {"Authorization": f"Bearer {verified['access_token']}"}

    secret = client.post("/api/v1/auth/mfa/setup", headers=headers).json()["secret"]
    enrolled = client.post(
        "/api/v1/auth/mfa/verify",
        json={"code": current_code(secret)},
        headers=headers,
    )
    assert enrolled.status_code == 200

    outbox.clear()
    pending = client.post(
        "/api/v1/auth/login",
        json={"email": "gwen.gov@state.gov", "password": "Password1"},
    ).json()
    assert pending["mfa_required"] is True
    assert outbox == []  # half-finished login: no alert yet

    challenge = client.post(
        "/api/v1/auth/mfa/challenge",
        json={"mfa_token": pending["mfa_token"], "code": current_code(secret)},
    )
    assert challenge.status_code == 200, challenge.text

    assert len(outbox) == 1
    assert outbox[0]["To"] == "gwen.gov@state.gov"
    assert "Your OrbitIQ account was successfully signed in." in _plain_body(outbox[0])



def test_login_notification_respects_the_user_preference(client, outbox):
    _register_student(client, email="prefs@orbitiq.ai")
    data = _verify_with_email_code(client, outbox, "prefs@orbitiq.ai").json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    client.put(
        "/api/users/settings",
        headers=headers,
        json={"notifications": {"security_alerts": False}},
    )
    stored = client.get("/api/users/settings", headers=headers).json()
    assert stored["notifications"]["security_alerts"] is False

    outbox.clear()
    client.post(
        "/api/v1/auth/login",
        json={"email": "prefs@orbitiq.ai", "password": "Password1"},
    )
    assert outbox == []  # opted out

    client.put(
        "/api/users/settings",
        headers=headers,
        json={"notifications": {"security_alerts": True}},
    )
    client.post(
        "/api/v1/auth/login",
        json={"email": "prefs@orbitiq.ai", "password": "Password1"},
    )
    assert len(outbox) == 1  # opted back in


def test_login_notification_can_be_switched_off_globally(client, outbox, monkeypatch):
    _register_student(client, email="globalswitch@orbitiq.ai")
    _verify_with_email_code(client, outbox, "globalswitch@orbitiq.ai")
    outbox.clear()

    monkeypatch.setattr(
        "app.config.settings.LOGIN_NOTIFICATION_ENABLED", False, raising=False
    )
    client.post(
        "/api/v1/auth/login",
        json={"email": "globalswitch@orbitiq.ai", "password": "Password1"},
    )
    assert outbox == []


def test_unverified_accounts_are_not_alerted(client, outbox):
    """Legacy login path: accounts without a verified address are skipped."""
    client.post(
        "/api/auth/register",
        json={
            "name": "Legacy User",
            "email": "legacy@orbitiq.ai",
            "password": "Password1",
            "confirm_password": "Password1",
        },
    )
    response = client.post(
        "/api/auth/login",
        json={"email": "legacy@orbitiq.ai", "password": "Password1"},
    )
    assert response.status_code == 200
    assert outbox == []



# ---------------------------------------------------------------------------
# 5. SMTP failure handling
# ---------------------------------------------------------------------------


def _failing_deliver(exc: Exception):
    def _deliver(message):  # noqa: ANN001 - mirrors mailer._deliver
        raise exc

    return _deliver


def test_smtp_auth_failure_does_not_crash_registration(client, outbox, monkeypatch):
    warnings: list[str] = []
    monkeypatch.setattr(
        mailer,
        "_deliver",
        _failing_deliver(
            smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")
        ),
    )
    monkeypatch.setattr(
        mailer.logger, "warning", lambda msg, *a, **k: warnings.append(str(msg))
    )
    response = _register_student(client, email="smtpdown@orbitiq.ai")

    # Registration still succeeds. SMTP is background-dispatched, so a
    # transient failure never holds up the authentication response.
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["requires_email_verification"] is True
    assert "demo_code" not in body
    # The failure is logged (without credentials) and never blocks the flow.
    assert any("delivery failed" in message for message in warnings)


def test_transient_smtp_eof_retries_once_with_a_fresh_delivery(outbox, monkeypatch):
    attempts = []

    def flaky_deliver(message):
        attempts.append(message)
        if len(attempts) == 1:
            raise ssl.SSLEOFError(8, "unexpected EOF while reading")

    monkeypatch.setattr(mailer, "_deliver", flaky_deliver)
    monkeypatch.setattr(mailer.time, "sleep", lambda _: None)
    result = mailer.send_email("retry@orbitiq.ai", "Subject", "Body", label="retry")

    assert result["sent"] is True
    assert len(attempts) == 2


def test_sensitive_url_values_are_redacted_before_logging():
    raw = (
        "/ws/notifications/user-1?token=jwt-secret&session_id=session-secret"
        "&otp=123456&code=654321"
    )
    safe = redact_sensitive_log_text(raw)
    assert "jwt-secret" not in safe
    assert "session-secret" not in safe
    assert "123456" not in safe
    assert "654321" not in safe
    assert "token=[REDACTED]" in safe


def test_configured_otp_is_queued_once_without_sending(monkeypatch):
    tasks = BackgroundTasks()
    monkeypatch.setattr(mailer, "is_configured", lambda: True)

    result = queue_otp(tasks, "queued@orbitiq.ai", "register", "123456", "Queued")

    assert result == {"queued": True}
    assert len(tasks.tasks) == 1


def test_smtp_failure_never_exposes_the_app_password(outbox, monkeypatch):
    monkeypatch.setattr(
        mailer,
        "_deliver",
        _failing_deliver(RuntimeError(f"535 auth rejected for {APP_PASSWORD}")),
    )
    result = mailer.send_email(
        "user@orbitiq.ai", "Subject", "Body", label="unit-failure"
    )
    assert result["sent"] is False
    assert result["delivered"] is False
    assert "***" in result["error"]
    assert APP_PASSWORD not in json.dumps(result)
    assert result["recipient"] == "u***@orbitiq.ai"



# ---------------------------------------------------------------------------
# SMTP connection checks (admin diagnostics)
# ---------------------------------------------------------------------------


def test_check_connection_reports_failure_without_secrets(monkeypatch):
    class BrokenSMTP:
        def __init__(self, *args, **kwargs):
            raise OSError(f"connection refused while using {APP_PASSWORD}")

    monkeypatch.setattr("app.config.settings.SMTP_PASSWORD", APP_PASSWORD, raising=False)
    monkeypatch.setattr(mailer.smtplib, "SMTP", BrokenSMTP)

    check = mailer.check_connection()
    assert check["ok"] is False
    assert check["provider"] == "gmail"
    assert check["host"] == "smtp.gmail.com"
    assert check["port"] == 587
    assert APP_PASSWORD not in json.dumps(check)
    assert "***" in check["error"]


def test_check_connection_success_reports_the_server(monkeypatch):
    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            self.esmtp_features = {"starttls": ""}
            self.started_tls = False
            self.quit_called = False

        def ehlo(self):
            return 250, b"smtp.gmail.com at your service, [127.0.0.1]"

        def starttls(self, context=None):
            self.started_tls = True

        def quit(self):
            self.quit_called = True

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    check = mailer.check_connection()
    assert check["ok"] is True
    assert check["starttls_supported"] is True
    assert check["transport"] == "starttls"
    assert "smtp.gmail.com" in check["server"]
    assert check["error"] is None



# ---------------------------------------------------------------------------
# Admin diagnostics: masked status + test send
# ---------------------------------------------------------------------------


def _admin_headers(client, outbox, email="admin.mail@orbitiq.ai"):
    """Register + verify a user, promote it to admin, return bearer headers."""
    from app.storage import get_db

    _register_student(client, email=email)
    data = _verify_with_email_code(client, outbox, email).json()
    get_db().update("users", data["user"]["id"], {"role": "admin"})
    return {"Authorization": f"Bearer {data['access_token']}"}


def test_admin_mail_status_is_masked_and_probe_is_opt_in(client, outbox, monkeypatch):
    headers = _admin_headers(client, outbox)
    outbox.clear()
    monkeypatch.setattr(
        mailer, "check_connection", lambda: {"ok": True, "note": "stubbed probe"}
    )

    response = client.get("/api/admin/mail/status?probe=true", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["enabled"] is True
    assert payload["provider"] == "gmail"
    assert payload["transport"] == "starttls"
    assert payload["username"] == MASKED_GMAIL_USER
    assert payload["connection"] == {"ok": True, "note": "stubbed probe"}
    assert APP_PASSWORD not in response.text
    assert payload["username"] != GMAIL_USER

    plain = client.get("/api/admin/mail/status", headers=headers).json()
    assert plain["connection"] is None


def test_admin_smtp_test_sends_an_email(client, outbox):
    headers = _admin_headers(client, outbox, email="admin.test@orbitiq.ai")
    outbox.clear()

    response = client.post("/api/admin/mail/test", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True
    assert response.json()["delivery"]["sent"] is True
    assert APP_PASSWORD not in response.text

    assert len(outbox) == 1
    assert outbox[0]["To"] == "admin.test@orbitiq.ai"
    assert outbox[0]["Subject"] == "OrbitIQ email delivery test"
    assert "Mail provider: gmail" in _plain_body(outbox[0])


def test_mail_diagnostics_require_admin(client, outbox):
    _register_student(client, email="plain.user@orbitiq.ai")
    data = _verify_with_email_code(client, outbox, "plain.user@orbitiq.ai").json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    assert client.get("/api/admin/mail/status", headers=headers).status_code == 403
    assert client.post("/api/admin/mail/test", headers=headers).status_code == 403



# ---------------------------------------------------------------------------
# Real transport (no stubbing): talk to a local SMTP server
# ---------------------------------------------------------------------------


class _LocalSMTPServer(threading.Thread):
    """Minimal SMTP server used to exercise the real ``mailer._deliver``."""

    def __init__(self):
        super().__init__(daemon=True)
        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(5)
        self.port = self._sock.getsockname()[1]
        self.received: list[str] = []
        self._stopped = False

    def run(self):  # pragma: no cover - runs in a helper thread
        while not self._stopped:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            with conn:
                self._session(conn)

    def _session(self, conn):  # pragma: no cover - network dialogue
        with conn.makefile("rwb") as stream:
            stream.write(b"220 localhost OrbitIQ test ESMTP\r\n")
            stream.flush()
            in_data = False
            while True:
                line = stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", "replace").rstrip("\r\n")
                upper = text.upper()
                if in_data:
                    if text == ".":
                        in_data = False
                        stream.write(b"250 OK queued\r\n")
                    else:
                        self.received.append(text)
                    stream.flush()
                    continue
                if upper.startswith(("EHLO", "HELO")):
                    stream.write(
                        b"250-localhost\r\n250-AUTH PLAIN LOGIN\r\n250 SIZE 10485760\r\n"
                    )
                elif upper.startswith("AUTH"):
                    stream.write(b"235 Authentication successful\r\n")
                elif upper.startswith("DATA"):
                    in_data = True
                    stream.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                elif upper.startswith("QUIT"):
                    stream.write(b"221 Bye\r\n")
                    stream.flush()
                    break
                else:
                    stream.write(b"250 OK\r\n")
                stream.flush()

    def stop(self):
        self._stopped = True
        try:
            self._sock.close()
        except OSError:
            pass


def test_real_transport_delivers_through_a_live_socket(client, monkeypatch):
    """End-to-end: config -> message -> socket -> SMTP dialogue -> DATA."""
    server = _LocalSMTPServer()
    server.start()
    monkeypatch.setattr("app.config.settings.MAIL_MODE", "true", raising=False)
    monkeypatch.setattr("app.config.settings.SMTP_HOST", "127.0.0.1", raising=False)
    monkeypatch.setattr("app.config.settings.SMTP_PORT", server.port, raising=False)
    monkeypatch.setattr(
        "app.config.settings.SMTP_USERNAME", "robot@localhost", raising=False
    )
    monkeypatch.setattr("app.config.settings.SMTP_PASSWORD", APP_PASSWORD, raising=False)
    monkeypatch.setattr("app.config.settings.SMTP_FROM", "robot@localhost", raising=False)
    monkeypatch.setattr("app.config.settings.SMTP_USE_STARTTLS", False, raising=False)
    monkeypatch.setattr("app.config.settings.SMTP_USE_SSL", False, raising=False)

    # The server does not offer STARTTLS, so probe first (EHLO only).
    check = mailer.check_connection()
    assert check["ok"] is True, check
    assert check["starttls_supported"] is False
    assert "localhost" in check["server"]

    try:
        response = _register_student(client, email="live.socket@orbitiq.ai")
        assert response.status_code == 201, response.text
        assert "demo_code" not in response.json()  # really delivered
    finally:
        server.join(timeout=3)
        server.stop()

    transcript = "\n".join(server.received)
    assert "Subject: Verify your OrbitIQ account" in transcript
    assert "To: live.socket@orbitiq.ai" in transcript
    assert "This code expires in 10 minutes" in transcript
    # the app password is only ever sent as an AUTH challenge, never in cleartext
    assert APP_PASSWORD not in transcript

