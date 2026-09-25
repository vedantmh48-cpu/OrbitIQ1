"""Public/system routes plus contact form."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..config import settings
from ..schemas import ContactRequest
from ..storage import get_db

router = APIRouter(tags=["system"])


@router.get("/api/health")
def health_public(db=Depends(get_db)):
    return {
        "ok": True,
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "storage": {
            "backend": _backend_name(db),
            "datasets": db.count("datasets", {}),
        },
    }


def _backend_name(db) -> str:
    from ..storage import get_db_backend

    return get_db_backend()


@router.get("/api/about")
def about():
    return {
        "name": settings.APP_NAME,
        "version": settings.VERSION,
        "capabilities": [
            "Natural-language query understanding",
            "Agentic processing (SAR / Optical / Temporal / Fusion)",
            "Optical, SAR, DEM, Vector, Time-Series, Tabular ingestion",
            "Change detection, classification, object detection, flood mapping",
            "Time-series analysis and multi-source fusion",
            "Interactive map + charts + downloadable reports",
        ],
        "demo_note": "Demo datasets are clearly labelled simulated when no real "
                     "providers are configured.",
    }


class ContactIn(BaseModel):
    name: str = ""


@router.post("/api/contact")
def contact(body: ContactRequest, db=Depends(get_db)):
    db.insert(
        "contacts",
        {
            "name": body.name,
            "email": body.email,
            "subject": body.subject,
            "message": body.message,
        },
    )
    return {"ok": True, "message": "Message received. Our team will get back to you."}