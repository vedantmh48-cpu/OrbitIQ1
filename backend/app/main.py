"""SatQuery AI - FastAPI application entry point.

Run locally with:
    uvicorn app.main:app --reload
(or: python run.py)
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import threading

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .errors import register_exception_handlers
from .middleware import LoggingAndRateLimitMiddleware, logger, setup_logging
from .routers import (
    admin,
    auth,
    auth_v1,
    change_analysis,
    datasets,
    geospatial,
    jobs_results,
    maps,
    queries,
    realtime_routes,
    reports,
    system,
    users,
)
from .security import decode_token
from .services.websocket_manager import manager
from .storage import get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    db = get_db()
    # Seed demo datasets on first boot for instant usability.
    if settings.demo_enabled():
        try:
            from .seed_data import seed_demo_data

            existing = db.count("datasets", {"source": "DEMO"})
            if existing == 0:
                n = seed_demo_data(db)
                logger.info("Seeded %d demo datasets", n)
            else:
                logger.info("Demo catalog already present (%d datasets).", existing)
        except Exception as exc:
            logger.warning("Demo seeding skipped: %s", exc)
    # Pre-warm the real-time cache so live queries are fast on first hit.
    # Run it in a daemon thread: startup must never block on external APIs
    # (a slow/unreachable upstream would otherwise delay `python run.py`
    # serving the app).
    def _prewarm_realtime() -> None:
        try:
            from .services import realtime as _rt

            _rt.fetch_earthquakes(hours=24, limit=20)
            _rt.fetch_weather()
            _rt.fetch_forecast()
        except Exception as exc:  # pragma: no cover - startup diagnostics only
            logger.warning("Realtime pre-warm skipped: %s", exc)

    threading.Thread(target=_prewarm_realtime, daemon=True).start()
    # Keep the map-type catalog in sync (document store + optional Postgres).
    try:
        from .map_catalog import sync_map_catalog

        sync_map_catalog()
    except Exception as exc:
        logger.warning("Map catalog sync skipped: %s", exc)
    logger.info(
        "SatQuery AI %s starting | env=%s | db=%s | demo=%s",
        settings.VERSION,
        settings.ENVIRONMENT,
        db.__class__.__name__,
        settings.DEMO_MODE,
    )
    # Report mail readiness (never the credentials themselves).
    try:
        from .services import mailer

        logger.info(
            "Mail: %s | %s:%s | %s | from=%s",
            "enabled" if mailer.is_configured() else "disabled (OTP demo_code fallback)",
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            mailer.transport_label(),
            settings.sender_header(),
        )
    except Exception as exc:  # pragma: no cover - diagnostics only
        logger.warning("Mail status unavailable: %s", exc)
    yield


app = FastAPI(
    title=f"{settings.APP_NAME} API",
    description=(
        "AI-powered natural-language satellite data query system.\n\n"
        "**Demo note:** without real provider credentials the platform serves "
        "clearly-labelled simulated datasets; connect Sentinel/Landsat/STAC "
        "providers via environment variables for real retrievals."
    ),
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingAndRateLimitMiddleware)

register_exception_handlers(app)

for r in (
    system,
    auth,
    auth_v1,
    users,
    queries,
    datasets,
    jobs_results,
    reports,
    geospatial,
    admin,
    realtime_routes,
    maps,
    change_analysis,
):
    app.include_router(r.router)


@app.get("/")
def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "health": "/api/health",
    }


# ---------------------------------------------------------------------------
# WebSocket: live job progress
# ---------------------------------------------------------------------------


@app.websocket("/ws/jobs/{job_id}")
async def job_socket(ws: WebSocket, job_id: str):
    token = ws.query_params.get("token", "")
    authenticated = False
    if token:
        try:
            payload = decode_token(token, "access")
            db = get_db()
            user = db.find_one("users", {"id": payload.get("sub")})
            authenticated = user is not None and user.get("active", True)
        except Exception:
            authenticated = False
    if not authenticated:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await manager.connect(job_id, ws)
    try:
        while True:
            # Keep-alive: ignore client pings, catch disconnects.
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(job_id, ws)
    except Exception:
        await manager.disconnect(job_id, ws)


@app.websocket("/ws/notifications/{user_id}")
async def notification_socket(ws: WebSocket, user_id: str):
    """Per-user security notifications (session revoked / password changed)."""
    token = ws.query_params.get("token", "")
    session_id = ws.query_params.get("session_id", "")
    authenticated = False
    if token:
        try:
            payload = decode_token(token, "access")
            if payload.get("sub") == user_id:
                from .auth_runtime import resolve_session

                if session_id:
                    _, _, error = resolve_session(session_id, touch=False)
                    authenticated = error is None
                else:
                    authenticated = False
        except Exception:
            authenticated = False
    if not authenticated:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await manager.connect_user(user_id, ws)
    try:
        while True:
            # Ignore client pings; catches disconnects.
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect_user(user_id, ws)
    except Exception:
        await manager.disconnect_user(user_id, ws)


@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(status_code=404, content={"error": True, "detail": "Endpoint not found."})