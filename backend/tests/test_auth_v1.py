"""v1 auth vertical slice tests: OTP registration, MFA, sessions, password change."""
import datetime as dt

from app.auth_store import get_auth_store
from app.auth_totp import current_code
from app.session_cache import get_session_cache


def _register_student(client, email="alice@satquery.ai", password="Password1"):
    return client.post(
        "/api/v1/auth/register",
        json={
            "account_type": "student",
            "full_name": "Alice Analyst",
            "email": email,
            "password": password,
            "confirm_password": password,
            "institution": "Geospatial University",
            "course": "Remote Sensing",
            "year_of_study": 3,
        },
    )


def _verify(client, email, code):
    return client.post("/api/v1/auth/verify-email", json={"email": email, "code": code})


# ---------------------------------------------------------------------------
# Registration + OTP email verification
# ---------------------------------------------------------------------------


def test_register_student_requires_email_verification(client):
    r = _register_student(client)
    assert r.status_code == 201
    body = r.json()
    assert body["requires_email_verification"] is True
    assert body["user"]["account_type"] == "student"
    assert body["user"]["email_verified"] is False
    assert "demo_code" in body  # demo mode delivers the code inline
    assert len(body["demo_code"]) == 6

    # Login before verification is blocked with a specific code.
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@satquery.ai", "password": "Password1"},
    )
    assert r.status_code == 403
    assert r.json()["code"] == "EMAIL_NOT_VERIFIED"

    # Wrong code is rejected.
    r = _verify(client, "alice@satquery.ai", "000000")
    assert r.status_code == 400

    # Correct code verifies the account AND issues a session.
    r = _verify(client, "alice@satquery.ai", body["demo_code"])
    assert r.status_code == 200
    data = r.json()
    assert data["user"]["email_verified"] is True
    assert data["access_token"] and data["refresh_token"] and data["session_id"]

    me = client.get("/api/users/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "alice@satquery.ai"


def test_register_duplicate_email_conflict(client):
    _register_student(client, email="alice@satquery.ai")
    r = _register_student(client, email="alice@satquery.ai")
    assert r.status_code == 409


def test_resend_verification_email(client):
    _register_student(client, email="carol@satquery.ai")
    r = client.post("/api/v1/auth/verify-email/resend", json={"email": "carol@satquery.ai"})
    assert r.status_code == 200
    assert "demo_code" in r.json()


def test_register_validation_for_role_payloads(client):
    # GIS analyst requires the employer / tool fields.
    r = client.post(
        "/api/v1/auth/register",
        json={"account_type": "gis_analyst", "full_name": "G", "email": "g@x.ai", "password": "Password1"},
    )
    assert r.status_code == 422
    # Organization requires a valid official domain.
    r = client.post(
        "/api/v1/auth/register",
        json={
            "account_type": "organization",
            "org_name": "Vector Corps",
            "org_type": "private",
            "official_domain": "not-a-domain",
            "admin_name": "Ava Admin",
            "admin_email": "ava@vectorcorps.com",
            "team_size": 12,
            "intended_use": "Track flooding in coastal regions.",
            "password": "Password1",
            "confirm_password": "Password1",
        },
    )
    assert r.status_code == 422
# ---------------------------------------------------------------------------
# MFA (TOTP)
# ---------------------------------------------------------------------------


def _register_org_gov(client, email="gov@state.gov"):
    return client.post(
        "/api/v1/auth/register",
        json={
            "account_type": "organization",
            "org_name": "State Defense Bureau",
            "org_type": "defense",
            "official_domain": "state.gov",
            "admin_name": "Gwen Gov",
            "admin_email": email,
            "team_size": 200,
            "intended_use": "National emergency response mapping.",
            "password": "Password1",
            "confirm_password": "Password1",
        },
    )


def test_mfa_required_for_gov_defense_org(client):
    r = _register_org_gov(client)
    assert r.status_code == 201
    assert r.json()["user"]["mfa_required"] is True

    r = _verify(client, "gov@state.gov", r.json()["demo_code"])
    assert r.status_code == 200
    access = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {access}"}

    # Defense org cannot raise its idle timeout above the 15 min clamp
    # and never receives a "Never"/60 min option.
    r = client.put(
        "/api/v1/auth/inactivity-timeout",
        json={"inactivity_timeout_minutes": 60},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["inactivity_timeout_minutes"] == 15
    assert r.json()["options"] == [5, 15]

    # Login forces MFA -> the user must enrol first.
    r = client.post("/api/v1/auth/login", json={"email": "gov@state.gov", "password": "Password1"})
    assert r.status_code == 200
    assert r.json()["mfa_setup_required"] is True
    setup_token = r.json()["mfa_token"]

    # Enrol a TOTP secret.
    r = client.post("/api/v1/auth/mfa/setup", headers=headers)
    assert r.status_code == 200
    secret = r.json()["secret"]
    assert r.json()["otpauth_url"].startswith("otpauth://totp/")

    r = client.post("/api/v1/auth/mfa/verify", json={"code": "123456"}, headers=headers)
    assert r.status_code == 400  # wrong code

    r = client.post("/api/v1/auth/mfa/verify", json={"code": current_code(secret)}, headers=headers)
    assert r.status_code == 200
    assert r.json()["mfa_enabled"] is True

    # Complete the pending login challenge with a valid TOTP.
    r = client.post(
        "/api/v1/auth/mfa/challenge",
        json={"mfa_token": setup_token, "code": current_code(secret)},
    )
    assert r.status_code == 200
    assert r.json()["access_token"] and r.json()["user"]["mfa_enabled"]

    # Second login now asks for the TOTP directly.
    r = client.post("/api/v1/auth/login", json={"email": "gov@state.gov", "password": "Password1"})
    assert r.status_code == 200
    assert r.json()["mfa_required"] is True
    r = client.post(
        "/api/v1/auth/mfa/challenge",
        json={"mfa_token": r.json()["mfa_token"], "code": "000000"},
    )
    assert r.status_code == 401
    assert r.json()["code"] == "MFA_INVALID"
# ---------------------------------------------------------------------------
# Sessions & revocation
# ---------------------------------------------------------------------------


def _verified_student(client, email="sess@satquery.ai"):
    _register_student(client, email=email)
    r = client.post("/api/v1/auth/verify-email/resend", json={"email": email})
    r = client.post("/api/v1/auth/verify-email", json={"email": email, "code": r.json()["demo_code"]})
    return r.json()


def test_sessions_list_and_revoke(client):
    data = _verified_student(client)
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    r = client.get("/api/v1/auth/sessions", headers=headers)
    assert r.status_code == 200
    sessions = r.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["current"] is True
    assert sessions[0]["device_label"]

    # Second concurrent session via a fresh login.
    r = client.post("/api/v1/auth/login", json={"email": "sess@satquery.ai", "password": "Password1"})
    second = r.json()
    second_headers = {"Authorization": f"Bearer {second['access_token']}"}

    r = client.get("/api/v1/auth/sessions", headers=headers)
    assert len(r.json()["sessions"]) == 2
    other = next(s for s in r.json()["sessions"] if not s["current"])

    # Revoke the other session -> it is immediately forbidden.
    r = client.delete(f"/api/v1/auth/sessions/{other['session_id']}", headers=headers)
    assert r.status_code == 200
    assert client.get("/api/users/me", headers=second_headers).status_code == 401

    # Revoke all other sessions.
    first_keep = client.post(
        "/api/v1/auth/login", json={"email": "sess@satquery.ai", "password": "Password1"}
    ).json()
    first_headers = {"Authorization": f"Bearer {first_keep['access_token']}"}
    r = client.post("/api/v1/auth/sessions/revoke-all", headers=first_headers)
    assert r.status_code == 200
    assert client.get("/api/users/me", headers=headers).status_code == 401

    # Refresh flow: valid refresh issues a token; revoked refresh is refused.
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": second["refresh_token"]})
    assert r.status_code == 401
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": first_keep["refresh_token"]})
    assert r.status_code == 200


def test_heartbeat_refreshes_last_seen(client):
    data = _verified_student(client)
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    r = client.post("/api/v1/auth/heartbeat", headers=headers)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["inactivity_timeout_minutes"] == 15
# ---------------------------------------------------------------------------
# Password change (403 on wrong current password, OTP-gated commit)
# ---------------------------------------------------------------------------


def test_change_password_flow_revokes_other_sessions(client):
    data = _verified_student(client)
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    # Wrong current password -> 403.
    r = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "wrong", "new_password": "FreshPass1", "confirm_password": "FreshPass1"},
    )
    assert r.status_code == 403
    assert r.json()["code"] == "CURRENT_PASSWORD_INCORRECT"

    # Second session (will be revoked on commit).
    second = client.post(
        "/api/v1/auth/login", json={"email": "sess@satquery.ai", "password": "Password1"}
    ).json()
    second_headers = {"Authorization": f"Bearer {second['access_token']}"}

    r = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "Password1", "new_password": "FreshPass1", "confirm_password": "FreshPass1"},
    )
    assert r.status_code == 200
    change_id = r.json()["password_change_id"]
    otp = r.json()["demo_code"]

    # Wrong OTP rejected.
    r = client.post(
        "/api/v1/auth/change-password/verify",
        headers=headers,
        json={"password_change_id": change_id, "otp_code": "000000"},
    )
    assert r.status_code == 400

    # Correct OTP commits the change and revokes the other device.
    r = client.post(
        "/api/v1/auth/change-password/verify",
        headers=headers,
        json={"password_change_id": change_id, "otp_code": otp},
    )
    assert r.status_code == 200
    assert r.json()["revoked_sessions"] >= 1
    assert client.get("/api/users/me", headers=second_headers).status_code == 401

    # New password works, old one no longer does.
    r = client.post("/api/v1/auth/login", json={"email": "sess@satquery.ai", "password": "FreshPass1"})
    assert r.status_code == 200
    r = client.post("/api/v1/auth/login", json={"email": "sess@satquery.ai", "password": "Password1"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Server-side inactivity enforcement
# ---------------------------------------------------------------------------


def test_inactive_session_rejected_on_request(client):
    data = _verified_student(client)
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    store = get_auth_store()

    session = store.get_session(data["session_id"])
    assert session is not None
    # Age the cached session's last_seen_at beyond the inactivity window.
    stale = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=30)).isoformat()
    store.update_session(data["session_id"], {"last_seen_at": stale})
    cache = get_session_cache()
    payload = dict(cache.get(data["session_id"]) or {})
    payload["last_seen_at"] = stale
    cache.set(data["session_id"], payload, 3600)

    r = client.get("/api/users/me", headers=headers)
    assert r.status_code == 401
    assert r.json()["code"] == "SESSION_INACTIVE"

    # The expired session was revoked server side.
    assert store.get_session(data["session_id"])["revoked"] is True