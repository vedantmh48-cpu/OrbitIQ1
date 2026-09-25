"""User profile, settings and account management routes."""
from __future__ import annotations

import jwt
from fastapi import APIRouter, Depends, HTTPException

from ..auth_store import get_auth_store
from ..deps import get_current_user
from ..schemas import ProfileUpdate, UserSettingsUpdate
from ..security import verify_password
from ..storage import get_db

router = APIRouter(prefix="/api/users", tags=["users"])


def _read_user(user_id: str) -> dict | None:
    """Read a user from the v1 auth store, falling back to the legacy DB."""
    store = get_auth_store()
    user = store.get_user(user_id)
    if user is not None:
        return user
    db = get_db()
    raw = db.find_one("users", {"id": user_id})
    if not raw:
        # Legacy docs may be keyed by the document id already.
        raw = db.find_one("users", {"email": user_id})
    return raw


def _patch_user(user_id: str, patch: dict) -> None:
    store = get_auth_store()
    if store.get_user(user_id) is not None:
        store.update_user(user_id, patch)
        return
    get_db().update("users", user_id, patch)


def _public(user: dict) -> dict:
    return {
        "id": user["id"],
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "role": user.get("role", "user"),
        "account_type": user.get("account_type", "student"),
        "org_type": user.get("org_type"),
        "bio": (user.get("profile") or {}).get("bio", ""),
        "organization": (user.get("profile") or {}).get("institution") or (user.get("profile") or {}).get("employer") or "",
        "created_at": user.get("created_at"),
        "email_verified": user.get("email_verified", False),
        "mfa_enabled": user.get("mfa_enabled", False),
        "inactivity_timeout_minutes": user.get("inactivity_timeout_minutes"),
    }


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return _public(_read_user(user["id"]) or user)


@router.put("/me")
def update_profile(
    body: ProfileUpdate,
    user: dict = Depends(get_current_user),
):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if "email" in patch and patch["email"] != user["email"]:
        existing = get_auth_store().get_user_by_email(patch["email"]) or get_db().find_one(
            "users", {"email": patch["email"]}
        )
        if existing and existing.get("id") != user["id"]:
            raise HTTPException(status_code=409, detail="That email is already in use.")
    stored = _read_user(user["id"]) or user
    profile = dict(stored.get("profile") or {})
    # legacy flat fields
    for src, dst in (("bio", "bio"), ("organization", "organization")):
        if patch.get(src) is not None:
            profile[dst] = patch.pop(src)
    if profile:
        patch["profile"] = profile
    _patch_user(user["id"], patch)
    return _public(_read_user(user["id"]) or user)


@router.get("/settings")
def get_settings(user: dict = Depends(get_current_user)):
    stored = _read_user(user["id"]) or user
    return stored.get("settings") or {}


@router.put("/settings")
def update_settings(
    body: UserSettingsUpdate,
    user: dict = Depends(get_current_user),
):
    stored = _read_user(user["id"]) or user
    settings = dict(stored.get("settings") or {})
    patch = body.model_dump(exclude_none=True)
    for k, v in patch.items():
        if isinstance(v, dict):
            current = settings.get(k) or {}
            current.update(v)
            settings[k] = current
        else:
            settings[k] = v
    _patch_user(user["id"], {"settings": settings})
    return settings


@router.delete("/me")
def delete_account(
    body: dict = None,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    password = (body or {}).get("password", "")
    if password and not verify_password(password, user.get("password_hash") or user.get("password", "")):
        raise HTTPException(status_code=400, detail="Password does not match.")
    auth_notify = user.get("id")
    store = get_auth_store()
    in_auth_store = store.get_user(user["id"]) is not None
    # cascade: remove personal data
    for coll, query in [
        ("queries", {"user_id": user["id"]}),
        ("results", {"user_id": user["id"]}),
        ("jobs", {"user_id": user["id"]}),
        ("saved_analyses", {"user_id": user["id"]}),
        ("sessions", {"user_id": user["id"]}),
        ("settings", {"user_id": user["id"]}),
    ]:
        for doc in db.find(coll, query):
            db.delete(coll, doc["id"])
    if in_auth_store:
        store.delete_user_sessions(user["id"])
        store.delete_user(user["id"])
        from ..services.websocket_manager import notify_user

        notify_user(auth_notify, "account_deleted")
    else:
        # anonymise the user record (keeps referential FK-ish integrity)
        db.update("users", user["id"], {
            "name": "Deleted User",
            "email": f"deleted-{user['id'][:8]}@satquery.ai",
            "active": False,
            "deleted_at": _now(),
        })
    return {"ok": True, "message": "Account deleted."}


def _now() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat()