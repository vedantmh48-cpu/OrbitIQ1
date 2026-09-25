"""Admin routes: system health, users, seeding, storage stats."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..config import settings
from ..deps import require_admin
from ..middleware import logger
from ..schemas import AdminUserUpdate
from ..storage import get_db, get_db_backend

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/health")
def health(db=Depends(get_db)):
    return {
        "ok": True,
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "storage_backend": get_db_backend(),
        "demo_mode": settings.DEMO_MODE,
        "database": {
            "datasets": db.count("datasets", {}),
            "users": db.count("users", {}),
            "queries": db.count("queries", {}),
            "jobs": db.count("jobs", {}),
            "results": db.count("results", {}),
            "saved_analyses": db.count("saved_analyses", {}),
        },
    }


@router.get("/stats")
def stats(admin: dict = Depends(require_admin), db=Depends(get_db)):
    from collections import Counter

    queries = db.find("queries", {})
    results = db.find("results", {})
    users = db.find("users", {})
    agents = Counter(r.get("agent_plan", {}).get("agent_name", "unknown") for r in results)
    ops = Counter(r.get("op") for r in results)
    return {
        "total_users": len(users),
        "total_queries": len(queries),
        "total_results": len(results),
        "agents_used": dict(agents),
        "operations": dict(ops),
        "queries_24h": len(
            [q for q in queries if str(q.get("created_at", "")).startswith(_today())]
        ),
    }


def _today() -> str:
    import datetime

    return datetime.date.today().isoformat()


@router.get("/users")
def list_users(admin: dict = Depends(require_admin), db=Depends(get_db)):
    rows = db.find("users", {}, sort=[("created_at", -1)], limit=100)
    out = []
    for u in rows:
        out.append({
            "id": u["id"],
            "name": u.get("name"),
            "email": u.get("email"),
            "role": u.get("role"),
            "active": u.get("active", True),
            "created_at": u.get("created_at"),
        })
    return out


@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    body: AdminUserUpdate,
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    target = db.find_one("users", {"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if patch.get("role") == "admin" and admin["id"] == user_id:
        pass  # self-promotion allowed only for existing admins (already required)
    db.update("users", user_id, patch)
    logger.info("Admin %s updated user %s: %s", admin["id"][:8], user_id[:8], patch)
    return {"ok": True}


@router.post("/seed/demo")
def seed_demo(admin: dict = Depends(require_admin), db=Depends(get_db)):
    from ..seed_data import seed_demo_data

    count = seed_demo_data(db)
    return {"ok": True, "datasets_seeded": count, "message": "Demo datasets are ready."}


@router.post("/system/log-level")
def set_log_level(level: str, admin: dict = Depends(require_admin)):
    lvl = level.upper()
    if lvl not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        raise HTTPException(status_code=400, detail="Invalid log level.")
    from ..middleware import logger

    logger.setLevel(lvl)
    return {"ok": True, "level": lvl}


# ---------------------------------------------------------------------------
# E-mail diagnostics (SMTP / Gmail)
# ---------------------------------------------------------------------------


@router.get("/mail/status")
def mail_status(admin: dict = Depends(require_admin), probe: bool = False):
    """Secret-free mail configuration.

    ``?probe=true`` additionally opens a real SMTP connection (EHLO +
    STARTTLS, no authentication) so the relay can be verified end to end. The
    Gmail app password is never returned.
    """
    from ..services import mailer

    payload = mailer.status()
    payload["connection"] = mailer.check_connection() if probe else None
    return payload


@router.post("/mail/test")
def send_test_mail(to: str | None = None, admin: dict = Depends(require_admin)):
    """Send a test e-mail (defaults to the calling admin's own address)."""
    from ..services import mailer

    recipient = (to or admin.get("email") or "").strip()
    if not recipient:
        raise HTTPException(status_code=400, detail="No recipient address available.")
    delivery = mailer.send_template(
        "smtp_test",
        recipient,
        label="smtp_test",
        name=admin.get("name", ""),
        email=recipient,
    )
    logger.info(
        "Admin %s SMTP test to %s: sent=%s",
        admin["id"][:8],
        mailer.mask_email(recipient),
        delivery.get("sent"),
    )
    return {
        "ok": bool(delivery.get("sent")),
        "delivery": delivery,
        "mail": mailer.status(),
    }