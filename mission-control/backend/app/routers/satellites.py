"""Mission Control - fleet / satellite status endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas import SatelliteOut
from ..store import get_store

router = APIRouter(prefix="/api/satellites", tags=["satellites"])


@router.get("", response_model=list[SatelliteOut])
def list_satellites():
    return get_store().list_satellites()


@router.get("/{satellite_id}", response_model=SatelliteOut)
def get_satellite(satellite_id: str):
    sat = get_store().get_satellite(satellite_id)
    if sat is None:
        raise HTTPException(status_code=404, detail="Satellite not found")
    return sat