"""Mission Control - FastAPI application.

Serves the mission-ops REST API under /api and the static console frontend
(frontend/index.html + css/js) from the same origin, so the whole standalone
app runs with a single `python run.py`.

Run locally:
    uvicorn app.main:app --reload
(or: python run.py)
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .routers import alerts, missions, satellites, telemetry

logger = logging.getLogger("mission-control")

app = FastAPI(
    title=f"{config.APP_NAME} API",
    description=(
        "Mission-ops telemetry service for the SatQuery AI platform.\n\n"
        "Serves missions, fleet status, alerts and a live telemetry feed. "
        "The telemetry engine is a deterministic simulation so the console "
        "works without any external provider."
    ),
    version=config.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (missions, satellites, telemetry, alerts):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    return {
        "name": config.APP_NAME,
        "version": config.VERSION,
        "status": "nominal",
        "docs": "/docs",
    }


@app.get("/api/overview")
def overview():
    """Aggregated metrics for the console home screen (single round-trip)."""
    from .store import get_store

    store = get_store()
    missions = store.list_missions()
    sats = store.list_satellites()
    alerts = store.list_alerts()

    def count(pred):
        return sum(1 for s in sats if pred(s["status"]))

    return {
        "missions": {
            "total": len(missions),
            "inProgress": sum(1 for m in missions if m["status"] == "in-progress"),
            "holding": sum(1 for m in missions if m["status"] == "holding"),
            "queued": sum(1 for m in missions if m["status"] == "queued"),
            "planned": sum(1 for m in missions if m["status"] == "planned"),
            "completed": sum(1 for m in missions if m["status"] == "completed"),
            "aborted": sum(1 for m in missions if m["status"] == "aborted"),
        },
        "fleet": {
            "total": len(sats),
            "operational": count(lambda s: s == "operational"),
            "standby": count(lambda s: s == "standby"),
            "calibrating": count(lambda s: s == "calibrating"),
            "avgLinkHealth": round(
                sum(s["linkHealth"] for s in sats) / len(sats), 1
            ),
        },
        "alerts": {
            "total": len(alerts),
            "unacked": sum(1 for a in alerts if not a["acknowledged"]),
            "critical": sum(
                1 for a in alerts if not a["acknowledged"] and a["severity"] == "critical"
            ),
            "high": sum(
                1 for a in alerts if not a["acknowledged"] and a["severity"] == "high"
            ),
        },
    }


@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(status_code=404, content={"error": True, "detail": "Endpoint not found."})


# ---------------------------------------------------------------------------
# Static console (must be mounted last so /api routes win).
# ---------------------------------------------------------------------------
if config.FRONTEND_DIR.exists():
    app.mount(
        "/",
        StaticFiles(directory=str(config.FRONTEND_DIR), html=True),
        name="console",
    )
else:
    logger.warning(
        "Frontend directory not found at %s - serving API only.", config.FRONTEND_DIR
    )