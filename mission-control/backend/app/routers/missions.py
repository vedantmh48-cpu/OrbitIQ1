"""Mission Control - mission lifecycle endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas import MissionCreate, MissionOut, MissionUpdate
from ..store import get_store

router = APIRouter(prefix="/api/missions", tags=["missions"])


@router.get("", response_model=list[MissionOut])
def list_missions():
    return get_store().list_missions()


@router.post("", response_model=MissionOut, status_code=201)
def create_mission(payload: MissionCreate):
    return get_store().create_mission(payload.model_dump())


@router.get("/{mission_id}", response_model=MissionOut)
def get_mission(mission_id: str):
    mission = get_store().get_mission(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


@router.patch("/{mission_id}", response_model=MissionOut)
def update_mission(mission_id: str, payload: MissionUpdate):
    mission = get_store().update_mission(mission_id, payload.model_dump(exclude_none=True))
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


@router.delete("/{mission_id}", status_code=204)
def delete_mission(mission_id: str):
    if not get_store().delete_mission(mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")