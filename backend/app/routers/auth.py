"""Auth routes: register, login, refresh, logout, forgot/reset password."""
from __future__ import annotations

import datetime as dt
import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from ..auth_otp import queue_password_reset
from ..auth_runtime import queue_login_email
from ..config import settings
from ..deps import get_current_user
from ..middleware import logger
from ..schemas import (
    ForgotPasswordRequest,
    PasswordChangeRequest,
    ResetPasswordRequest,
    UserCreate,
    UserLogin,
)
from ..security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_reset_token,
    hash_password,
    hash_token,
    verify_password,
)
from ..storage import datetime_now, get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _tokens_for(db, user: dict) -> dict:
    access = create_access_token(user["id"], user.get("role", "user"))
    refresh = create_refresh_token(user["id"])
    jti = decode_token(refresh, "refresh")["jti"]
    now = dt.datetime.now(dt.timezone.utc)
    db.insert(
        "sessions",
        {
            "user_id": user["id"],
            "refresh_jti": jti,
            "revoked": False,
            "created_at": datetime_now(),
            "expires_at": (now + dt.timedelta(days=settings.JWT_REFRESH_TTL_DAYS)).isoformat(),
        },
    )
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


def _user_public(user: dict) -> dict:
    return {
        "id": user["id"],
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "role": user.get("role", "user"),
        "active": user.get("active", True),
        "created_at": user.get("created_at"),
    }


@router.post("/register", status_code=201)
def register(body: UserCreate, db=Depends(get_db)):
    if db.find_one("users", {"email": body.email}):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user_id = db.insert(
        "users",
        {
            "name": body.name.strip(),
            "email": body.email,
            "password": hash_password(body.password),
            "role": "user",
            "active": True,
            "email_verified": False,
            "settings": {
                "theme": "dark",
                "default_satellite_source": "demo",
                "default_data_type": "any",
                "map_preferences": {"base_layer": "dark", "show_labels": True},
                "notifications": {
                    "email_summary": True,
                    "job_updates": True,
                    "weekly_digest": False,
                },
            },
            "created_at": datetime_now(),
        },
    )
    user = db.find_one("users", {"id": user_id})
    tokens = _tokens_for(db, user)
    logger.info("New registration: %s (%s)", body.email, user_id[:8])
    return {"user": _user_public(user), **tokens}
@router.post("/login")
def login(body: UserLogin, request: Request, background_tasks: BackgroundTasks, db=Depends(get_db)):
    user = db.find_one("users", {"email": body.email})
    if not user or not verify_password(body.password, user.get("password", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if not user.get("active", True):
        raise HTTPException(status_code=403, detail="Account has been deactivated.")
    tokens = _tokens_for(db, user)
    # Same "new sign-in" security alert as the v1 login (best-effort).
    queue_login_email(background_tasks, user, request, mfa_used=False)
    logger.info("Login: %s", body.email)
    return {"user": _user_public(user), **tokens}


@router.post("/refresh")
def refresh(body: dict, db=Depends(get_db)):
    token = (body or {}).get("refresh_token", "")
    try:
        payload = decode_token(token, "refresh")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token.")
    session = db.find_one("sessions", {"refresh_jti": payload.get("jti"), "revoked": False})
    if not session:
        raise HTTPException(status_code=401, detail="Session revoked. Please sign in again.")
    user = db.find_one("users", {"id": payload.get("sub")})
    if not user or not user.get("active", True):
        raise HTTPException(status_code=401, detail="Account unavailable.")
    access = create_access_token(user["id"], user.get("role", "user"))
    return {"access_token": access, "token_type": "bearer"}


@router.post("/logout")
def logout(body: dict, db=Depends(get_db)):
    token = (body or {}).get("refresh_token", "")
    try:
        payload = decode_token(token, "refresh")
        session = db.find_one("sessions", {"refresh_jti": payload.get("jti")})
        if session:
            db.update("sessions", session["id"], {"revoked": True})
    except jwt.PyJWTError:
        pass
    return {"ok": True, "message": "Signed out."}


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest, background_tasks: BackgroundTasks, db=Depends(get_db)):
    response = {
        "ok": True,
        "message": (
            "If an account exists for this email, a reset link has been issued. "
            "(Without SMTP configured the link is returned below for local testing.)"
        ),
    }
    user = db.find_one("users", {"email": body.email})
    if not user:
        return response
    token = generate_reset_token()
    expires = (
        dt.datetime.now(dt.timezone.utc)
        + dt.timedelta(minutes=settings.PASSWORD_RESET_TTL_MINUTES)
    ).isoformat()
    db.update("users", user["id"], {
        "reset_token_hash": hash_token(token),
        "reset_token_expires": expires,
    })
    reset_link = f"{settings.APP_PUBLIC_URL}/reset-password?token={token}"
    if settings.mail_enabled():
        queue_password_reset(background_tasks, user["email"], reset_link, name=user.get("name", ""))
        # The request accepted delivery for dispatch. The actual SMTP outcome
        # is logged by the background mailer and never affects reset security.
        response["delivered"] = True
        logger.info(
            "Password reset e-mail for %s: queued=%s",
            body.email,
            response["delivered"],
        )
    else:
        # No SMTP configured: keep the local demo flow usable (the link is
        # logged and returned so the reset can still be completed offline).
        logger.info("Password reset requested for %s (mail disabled; demo link returned)", body.email)
        response["demo_reset_link"] = reset_link
    return response


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest, db=Depends(get_db)):
    token_hash = hash_token(body.token)
    user = None
    for u in db.find("users", {}):
        if u.get("reset_token_hash") == token_hash:
            user = u
            break
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset code.")
    expires = user.get("reset_token_expires")
    if expires and dt.datetime.fromisoformat(expires).replace(tzinfo=dt.timezone.utc) < dt.datetime.now(dt.timezone.utc):
        raise HTTPException(status_code=400, detail="This reset link has expired.")
    new_hash = hash_password(body.new_password)
    db.update("users", user["id"], {
        "password": new_hash,
        "password_hash": new_hash,  # keep v1 users in sync
        "password_changed_at": datetime_now(),
        "reset_token_hash": None,
        "reset_token_expires": None,
    })
    # Revoke every session so the reset is enforced everywhere.
    for s in db.find("sessions", {"user_id": user["id"]}):
        db.update("sessions", s["id"], {"revoked": True})
    return {"ok": True, "message": "Password updated. You can now sign in."}


@router.post("/change-password")
def change_password(
    body: PasswordChangeRequest,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    if not verify_password(body.current_password, user.get("password", "")):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    db.update("users", user["id"], {"password": hash_password(body.new_password)})
    for s in db.find("sessions", {"user_id": user["id"]}):
        db.update("sessions", s["id"], {"revoked": True})
    return {"ok": True, "message": "Password updated. Please sign in again."}
