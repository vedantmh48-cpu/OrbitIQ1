"""Mission Control - alert feed endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas import AlertAck, AlertOut
from ..store import get_store

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
def list_alerts():
    return get_store().list_alerts()


@router.patch("/{alert_id}", response_model=AlertOut)
def acknowledge_alert(alert_id: str, payload: AlertAck):
    alert = get_store().set_ack(alert_id, payload.acknowledged)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert