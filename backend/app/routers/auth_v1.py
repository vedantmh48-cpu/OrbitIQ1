"""v1 Auth & account-management routes for SatQuery AI.

Implements the full auth vertical slice:

* `/register`            - role-based registration + email OTP dispatch
* `/verify-email`        - 6-digit OTP email verification (enables logins)
* `/verify-email/resend`
* `/login`               - password + optional TOTP MFA challenge
* `/refresh`             - access-token refresh via rotated session hash
* `/logout`
* `/heartbeat`           - resets session activity timestamps (client & Redis)
* `/sessions`, `/sessions/{id}`, `/sessions/revoke-all`
* `/change-password`     - current-password re-check + OTP dispatch
* `/change-password/verify` - OTP-verified password change with session purge
* `/mfa/setup|verify|disable|challenge` - TOTP MFA lifecycle
* `/inactivity-timeout`  - per-user idle auto-logout window
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from ..auth_otp import generate_otp, queue_otp
from ..auth_runtime import (
    ERR_EMAIL_NOT_VERIFIED,
    ERR_MFA_INVALID,
    ERR_MFA_SETUP_REQUIRED,
    issue_session,
    queue_login_email,
    revoke_session,
    session_serialized,
)
from ..auth_schemas import (
    ChangePasswordRequest,
    ChangePasswordVerifyRequest,
    GisAnalystRegistration,
    InactivityTimeoutUpdate,
    LogoutRequest,
    MfaChallengeRequest,
    MfaVerifyRequest,
    OrganizationRegistration,
    RefreshRequest,
    RegistrationPayload,
    ResendVerificationRequest,
    ResearcherRegistration,
    StudentRegistration,
    UserLogin,
    VerifyEmailRequest,
)
from ..auth_store import (
    ACCOUNT_ORGANIZATION,
    clamp_inactivity_minutes,
    get_auth_store,
    inactivity_options_for,
    is_gov,
    user_public,
)
from ..auth_totp import generate_secret, otpauth_uri, validate_code
from ..config import settings
from ..deps import get_current_session, get_current_user
from ..errors import app_error
from ..middleware import logger
from ..security import (
    create_access_token,
    decode_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from ..session_cache import get_session_cache
from ..services.websocket_manager import notify_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth-v1"])

_MFA_TOKEN_TTL = 300  # seconds a half-authenticated login may wait


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def _registration_email(body) -> str:
    return (getattr(body, "email", None) or getattr(body, "admin_email", "")).strip().lower()


def _registration_profile(body) -> dict:
    if isinstance(body, StudentRegistration):
        return {
            "institution": body.institution,
            "course": body.course,
            "year_of_study": body.year_of_study,
        }
    if isinstance(body, ResearcherRegistration):
        return {
            "institution": body.institution,
            "research_field": body.research_field,
            "orcid": body.orcid or "",
            "profile_link": body.profile_link or "",
        }
    if isinstance(body, GisAnalystRegistration):
        return {
            "employer": body.employer,
            "job_title": body.job_title,
            "years_experience": body.years_experience,
            "primary_tools": body.primary_tools,
        }
    if isinstance(body, OrganizationRegistration):
        return {
            "org_name": body.org_name,
            "org_type": body.org_type,
            "official_domain": body.official_domain,
            "admin_name": body.admin_name,
            "admin_email": body.admin_email,
            "team_size": body.team_size,
            "intended_use": body.intended_use,
        }
    return {}


def _registration_user_doc(body) -> dict:
    """Translate a role-specific registration payload into a user record."""
    org_type = getattr(body, "org_type", None)
    account_type = body.account_type
    gov = is_gov(account_type, org_type)
    timeout = (
        settings.GOV_MAX_INACTIVITY_TIMEOUT_MINUTES
        if gov
        else settings.DEFAULT_INACTIVITY_TIMEOUT_MINUTES
    )
    name = getattr(body, "full_name", None) or getattr(body, "admin_name", None) or ""
    return {
        "name": name.strip(),
        "email": _registration_email(body),
        "password_hash": hash_password(body.password),
        "role": "user",
        "account_type": account_type,
        "org_type": org_type if account_type == ACCOUNT_ORGANIZATION else None,
        "active": True,
        "email_verified": False,
        "mfa_enabled": False,
        "mfa_required": gov,
        "inactivity_timeout_minutes": timeout,
        "profile": _registration_profile(body),
        "settings": {
            "theme": "dark",
            "default_satellite_source": "demo",
            "default_data_type": "any",
            "map_preferences": {"base_layer": "dark", "show_labels": True},
            "notifications": {"email_summary": True, "job_updates": True, "weekly_digest": False},
        },
        "password_changed_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
@router.post("/register", status_code=201)
def register(
    body: RegistrationPayload,
    request: Request,
    background_tasks: BackgroundTasks,
    store=Depends(get_auth_store),
):
    email = _registration_email(body)
    if store.get_user_by_email(email):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = store.create_user(_registration_user_doc(body))
    code = generate_otp()
    store.create_email_verification(user["id"], "register", code, settings.AUTH_OTP_TTL_MINUTES)
    otp = queue_otp(background_tasks, email, "register", code, name=user.get("name", ""))

    logger.info("New registration (%s): %s (%s)", body.account_type, email, user["id"][:8])
    response = {
        "user": user_public(user),
        "requires_email_verification": True,
        "email": email,
        "verification_expires_in_minutes": settings.AUTH_OTP_TTL_MINUTES,
        "verification_purpose": "register",
    }
    if otp.get("demo_code"):
        response["demo_code"] = otp["demo_code"]
    return response


@router.post("/verify-email")
def verify_email(
    body: VerifyEmailRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    store=Depends(get_auth_store),
):
    user = store.get_user_by_email(body.email)
    if not user:
        raise HTTPException(status_code=404, detail="No account exists for this email address.")
    if user.get("email_verified"):
        raise HTTPException(status_code=409, detail="This email address is already verified.")

    status = store.consume_email_verification(user["id"], "register", body.code)
    if status != "ok":
        raise HTTPException(status_code=400, detail="Invalid or expired verification code.")

    store.update_user(user["id"], {"email_verified": True})
    verified = store.get_user(user["id"])
    tokens = issue_session(store, verified, request)
    # Verification completes by issuing an authenticated session, so it is a
    # successful sign-in for the purpose of the new-sign-in security alert.
    queue_login_email(background_tasks, verified, request, mfa_used=False)
    logger.info("Email verified: %s", body.email)
    return {"user": user_public(verified), **tokens}


@router.post("/verify-email/resend")
def resend_verification(
    body: ResendVerificationRequest,
    background_tasks: BackgroundTasks,
    store=Depends(get_auth_store),
):
    response: dict = {
        "ok": True,
        "message": "If an account exists, a new verification code has been sent.",
    }
    user = store.get_user_by_email(body.email)
    if user and not user.get("email_verified"):
        code = generate_otp()
        store.create_email_verification(user["id"], "register", code, settings.AUTH_OTP_TTL_MINUTES)
        otp = queue_otp(background_tasks, body.email, "register", code, name=user.get("name", ""))
        if otp.get("demo_code"):
            response["demo_code"] = otp["demo_code"]
    return response
# ---------------------------------------------------------------------------
# Sign-in, refresh, logout
# ---------------------------------------------------------------------------


def _mfa_token_for(user: dict, purpose: str) -> str:
    token = secrets.token_urlsafe(24)
    get_session_cache().set(
        f"satquery:mfa:{token}",
        {"user_id": user["id"], "purpose": purpose},
        _MFA_TOKEN_TTL,
    )
    return token


@router.post("/login")
def login(body: UserLogin, request: Request, background_tasks: BackgroundTasks, store=Depends(get_auth_store)):
    user = store.get_user_by_email(body.email)
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if not user.get("active", True):
        raise HTTPException(status_code=403, detail="This account has been deactivated.")
    if not user.get("email_verified"):
        raise app_error(
            403,
            "Please verify your email address before signing in. A verification code was sent on registration.",
            code=ERR_EMAIL_NOT_VERIFIED,
        )

    # MFA gate: enabled accounts must complete a TOTP challenge; gov/defense
    # organizations must enrol before their first login proceeds.
    if user.get("mfa_required") or user.get("mfa_enabled"):
        if not user.get("mfa_enabled"):
            mfa_token = _mfa_token_for(user, "login_setup")
            return {
                "mfa_setup_required": True,
                "mfa_token": mfa_token,
                "email": body.email,
                "user": user_public(user),
            }
        mfa_token = _mfa_token_for(user, "login")
        return {
            "mfa_required": True,
            "mfa_token": mfa_token,
            "email": body.email,
            "expires_in_seconds": _MFA_TOKEN_TTL,
        }

    tokens = issue_session(store, user, request)
    queue_login_email(background_tasks, user, request, mfa_used=False)
    logger.info("Login: %s", body.email)
    return {"user": user_public(user), **tokens}


@router.post("/mfa/challenge")
def mfa_challenge(body: MfaChallengeRequest, request: Request, background_tasks: BackgroundTasks, store=Depends(get_auth_store)):
    attempt = get_session_cache().get(f"satquery:mfa:{body.mfa_token}")
    if not attempt or attempt.get("purpose") not in ("login", "login_setup"):
        raise HTTPException(status_code=400, detail="This sign-in attempt has expired. Please try again.")
    user = store.get_user(attempt.get("user_id"))
    if not user or not user.get("active", True):
        raise HTTPException(status_code=401, detail="Account unavailable.")
    if not user.get("mfa_enabled") or not user.get("mfa_secret"):
        raise app_error(
            403,
            "MFA is not enabled for this account yet.",
            code=ERR_MFA_SETUP_REQUIRED,
        )
    if not validate_code(user["mfa_secret"], body.code):
        raise app_error(401, "Invalid authenticator code.", code=ERR_MFA_INVALID)
    get_session_cache().delete(f"satquery:mfa:{body.mfa_token}")
    tokens = issue_session(store, user, request)
    queue_login_email(background_tasks, user, request, mfa_used=True)
    return {"user": user_public(user), **tokens}
@router.post("/refresh")
def refresh(body: RefreshRequest, request: Request, store=Depends(get_auth_store)):
    refresh = (body.refresh_token or "").strip()
    if not refresh:
        raise HTTPException(status_code=401, detail="Invalid refresh token.")
    session = store.get_session_by_refresh_hash(hash_refresh_token(refresh))
    if not session or session.get("revoked"):
        raise HTTPException(status_code=401, detail="Session revoked. Please sign in again.")
    if session.get("expires_at") and datetime.fromisoformat(
        str(session["expires_at"])
    ).replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        revoke_session(store, session["session_id"], session.get("user_id"))
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    user = store.get_user(session.get("user_id"))
    if not user or not user.get("active", True):
        raise HTTPException(status_code=401, detail="Account unavailable.")
    access = create_access_token(user["id"], user.get("role", "user"), session["session_id"])
    return {
        "access_token": access,
        "token_type": "bearer",
        "session_id": session["session_id"],
        "user": user_public(user),
    }


@router.post("/logout")
def logout(body: LogoutRequest, request: Request, store=Depends(get_auth_store)):
    session_id = None
    user_id = None
    if body.refresh_token:
        s = store.get_session_by_refresh_hash(hash_refresh_token(body.refresh_token))
        if s:
            session_id, user_id = s["session_id"], s["user_id"]
    if not session_id:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            try:
                payload = decode_token(auth[7:], "access")
                if payload.get("sid"):
                    s = store.get_session(payload["sid"])
                    if s:
                        session_id, user_id = s["session_id"], payload.get("sub")
            except Exception:
                pass
    if session_id:
        revoke_session(store, session_id, user_id)
    return {"ok": True, "message": "Signed out."}


@router.post("/heartbeat")
def heartbeat(
    session=Depends(get_current_session),
    user=Depends(get_current_user),
    store=Depends(get_auth_store),
):
    """Resets both the DB and Redis/cache ``last_seen_at`` timestamps."""
    from ..storage import datetime_now

    now = datetime_now()
    store.update_session(session["session_id"], {"last_seen_at": now})
    cache = get_session_cache()
    payload = dict(cache.get(session["session_id"]) or {})
    payload.update({"last_seen_at": now, "expires_at": session["expires_at"], "revoked": False})
    cache.set(session["session_id"], payload, _ttl_for(session))
    return {
        "ok": True,
        "last_seen_at": now,
        "expires_at": session["expires_at"],
        "inactivity_timeout_minutes": user.get("inactivity_timeout_minutes"),
    }


def _ttl_for(session: dict) -> int:
    try:
        seconds = int(
            (
                datetime.fromisoformat(str(session["expires_at"])).replace(tzinfo=timezone.utc)
                - datetime.now(timezone.utc)
            ).total_seconds()
        )
        return max(1, min(seconds, 60 * 24 * 3600))
    except Exception:
        return settings.JWT_REFRESH_TTL_DAYS * 24 * 3600
# ---------------------------------------------------------------------------
# Active sessions
# ---------------------------------------------------------------------------


@router.get("/sessions")
def list_sessions(
    user=Depends(get_current_user),
    session=Depends(get_current_session),
    store=Depends(get_auth_store),
):
    return {
        "sessions": [
            session_serialized(s, session["session_id"])
            for s in store.get_user_sessions(user["id"])
            if not s.get("revoked")
        ]
    }


@router.delete("/sessions/{session_id}")
def revoke_one_session(
    session_id: str,
    user=Depends(get_current_user),
    session=Depends(get_current_session),
    store=Depends(get_auth_store),
):
    target = store.get_session(session_id)
    if not target or target.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Session not found.")
    if target["session_id"] == session["session_id"]:
        raise HTTPException(status_code=400, detail="Use Sign Out to end the current session.")
    revoke_session(store, target["session_id"], user["id"])
    return {"ok": True, "message": "Session signed out."}


@router.post("/sessions/revoke-all")
def revoke_other_sessions(
    user=Depends(get_current_user),
    session=Depends(get_current_session),
    store=Depends(get_auth_store),
):
    revoked = 0
    for s in store.get_user_sessions(user["id"]):
        if s["session_id"] != session["session_id"] and not s.get("revoked"):
            revoke_session(store, s["session_id"], user["id"])
            revoked += 1
    return {"ok": True, "revoked_count": revoked}


# ---------------------------------------------------------------------------
# Password change (current password re-check -> OTP -> commit)
# ---------------------------------------------------------------------------


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
    store=Depends(get_auth_store),
):
    if not verify_password(body.current_password, user.get("password_hash", "")):
        raise app_error(
            403,
            "Current password is incorrect.",
            code="CURRENT_PASSWORD_INCORRECT",
        )
    code = generate_otp()
    store.create_email_verification(
        user["id"], "password_change", code, settings.AUTH_PASSWORD_CHANGE_TTL_MINUTES
    )
    change_id = secrets.token_urlsafe(16)
    get_session_cache().set(
        f"satquery:pc:{change_id}",
        {
            "user_id": user["id"],
            "password_hash": hash_password(body.new_password),
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        settings.AUTH_PASSWORD_CHANGE_TTL_MINUTES * 60,
    )
    otp = queue_otp(background_tasks, user["email"], "password_change", code, name=user.get("name", ""))
    response = {
        "ok": True,
        "password_change_id": change_id,
        "expires_in_minutes": settings.AUTH_PASSWORD_CHANGE_TTL_MINUTES,
        "message": "A 6-digit verification code was sent to your email.",
    }
    if otp.get("demo_code"):
        response["demo_code"] = otp["demo_code"]
    return response


@router.post("/change-password/verify")
def change_password_verify(
    body: ChangePasswordVerifyRequest,
    session=Depends(get_current_session),
    user=Depends(get_current_user),
    store=Depends(get_auth_store),
):
    pending = get_session_cache().get(f"satquery:pc:{body.password_change_id}")
    if not pending or pending.get("user_id") != user["id"]:
        raise HTTPException(status_code=400, detail="This password change request has expired.")
    status = store.consume_email_verification(user["id"], "password_change", body.otp_code)
    if status != "ok":
        raise HTTPException(status_code=400, detail="Invalid or expired verification code.")

    store.update_user(
        user["id"],
        {
            "password_hash": pending["password_hash"],
            "password_changed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    # Revoke all other sessions; the current one stays active.
    count = store.revoke_user_sessions_except(user["id"], session["session_id"])
    for s in store.get_user_sessions(user["id"]):
        if s.get("revoked"):
            get_session_cache().delete(s["session_id"])
    get_session_cache().delete(f"satquery:pc:{body.password_change_id}")
    notify_user(user["id"], "password_changed", except_session_id=session["session_id"])
    logger.info("Password changed for %s (%d other sessions revoked)", user["email"], count)
    return {
        "ok": True,
        "message": "Password updated. All other devices were signed out.",
        "revoked_sessions": count,
    }
# ---------------------------------------------------------------------------
# MFA (TOTP) lifecycle
# ---------------------------------------------------------------------------


@router.post("/mfa/setup")
def mfa_setup(user=Depends(get_current_user)):
    secret = generate_secret()
    get_session_cache().set(
        f"satquery:mfa-pending:{user['id']}",
        {"secret": secret, "created_at": datetime.now(timezone.utc).isoformat()},
        600,
    )
    return {
        "secret": secret,
        "otpauth_url": otpauth_uri(secret, user["email"]),
        "expires_in_seconds": 600,
        "hint": "Scan the QR code with your authenticator app or enter the secret manually.",
    }


@router.post("/mfa/verify")
def mfa_verify(
    body: MfaVerifyRequest,
    user=Depends(get_current_user),
    store=Depends(get_auth_store),
):
    pending = get_session_cache().get(f"satquery:mfa-pending:{user['id']}")
    if not pending or not pending.get("secret"):
        raise HTTPException(status_code=400, detail="No pending MFA setup. Request a new secret first.")
    if not validate_code(pending["secret"], body.code):
        raise app_error(400, "Invalid authenticator code.", code=ERR_MFA_INVALID)
    store.update_user(user["id"], {"mfa_secret": pending["secret"], "mfa_enabled": True})
    get_session_cache().delete(f"satquery:mfa-pending:{user['id']}")
    return {"ok": True, "mfa_enabled": True, "message": "Two-factor authentication enabled."}


@router.post("/mfa/disable")
def mfa_disable(
    body: MfaVerifyRequest,
    user=Depends(get_current_user),
    store=Depends(get_auth_store),
):
    if not user.get("mfa_enabled") or not user.get("mfa_secret"):
        raise HTTPException(status_code=400, detail="Two-factor authentication is not enabled.")
    if not validate_code(user["mfa_secret"], body.code):
        raise app_error(401, "Invalid authenticator code.", code=ERR_MFA_INVALID)
    store.update_user(user["id"], {"mfa_secret": None, "mfa_enabled": False})
    return {"ok": True, "mfa_enabled": False, "message": "Two-factor authentication disabled."}


@router.put("/inactivity-timeout")
def set_inactivity_timeout(
    body: InactivityTimeoutUpdate,
    user=Depends(get_current_user),
    store=Depends(get_auth_store),
):
    minutes = clamp_inactivity_minutes(
        user.get("account_type", "student"),
        body.inactivity_timeout_minutes,
        user.get("org_type"),
    )
    store.update_user(user["id"], {"inactivity_timeout_minutes": minutes})
    updated = store.get_user(user["id"])
    return {
        "inactivity_timeout_minutes": updated.get("inactivity_timeout_minutes"),
        "options": inactivity_options_for(
            user.get("account_type", "student"), user.get("org_type")
        ),
    }
