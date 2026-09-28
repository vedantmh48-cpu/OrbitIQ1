"""Mission Control - Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Missions
# ---------------------------------------------------------------------------


class MissionCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    satellite: str = Field(..., min_length=1, max_length=40)
    target: str = Field("", max_length=120)
    region: str = Field("", max_length=120)
    priority: str = Field("normal", pattern="^(low|normal|high|critical)$")
    objective: str = Field("", max_length=400)


class MissionUpdate(BaseModel):
    status: str | None = Field(
        None, pattern="^(planned|queued|in-progress|holding|completed|aborted)$"
    )
    progress: int | None = Field(None, ge=0, le=100)
    phase: str | None = Field(None, max_length=80)
    eta: str | None = Field(None, max_length=40)


class MissionOut(BaseModel):
    id: str
    name: str
    code: str
    satellite: str
    target: str
    region: str
    priority: str
    status: str
    progress: int
    phase: str
    eta: str
    objective: str
    owner: str
    createdAt: datetime
    updatedAt: datetime


# ---------------------------------------------------------------------------
# Fleet / satellites
# ---------------------------------------------------------------------------


class SatelliteOut(BaseModel):
    id: str
    name: str
    catalog: str
    orbit: str
    altitudeKm: float
    inclinationDeg: float
    status: str
    linkHealth: int
    downlink: float
    battery: int
    instruments: list[str]
    lastPass: str


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


class AlertOut(BaseModel):
    id: str
    severity: str
    source: str
    title: str
    message: str
    createdAt: datetime
    acknowledged: bool


class AlertAck(BaseModel):
    acknowledged: bool = True


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------


class TelemetrySample(BaseModel):
    t: int  # epoch seconds
    link: float  # Mbps on the active downlink
    battery: int  # percent
    temp: float  # °C bus temperature
    altitude: float  # km
    signal: int  # dBm
    data: float  # MB accumulated this pass


class TelemetryOut(BaseModel):
    satellite: str
    sampledAt: int
    current: TelemetrySample
    history: list[TelemetrySample]