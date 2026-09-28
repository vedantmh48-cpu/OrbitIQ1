"""Mission Control - live telemetry endpoints.

The store advances a deterministic smooth random walk on every poll, so the
console gets a believable live feed with zero external dependencies.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas import TelemetryOut
from ..store import get_store

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.get("/{satellite_id}", response_model=TelemetryOut)
def telemetry(satellite_id: str):
    snapshot = get_store().telemetry_snapshot(satellite_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Satellite not found")
    return snapshot