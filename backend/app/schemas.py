"""Pydantic request/response schemas with validation rules."""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_email(value: str) -> str:
    value = value.strip().lower()
    if not EMAIL_RE.match(value):
        raise ValueError("Please provide a valid email address")
    return value


def validate_password(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters")
    return value


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str
    password: str
    confirm_password: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return validate_email(v)

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        return validate_password(v)

    @model_validator(mode="after")
    def _match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class UserLogin(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return validate_email(v)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class ForgotPasswordRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return validate_email(v)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10)
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def _password(cls, v: str) -> str:
        return validate_password(v)

    @model_validator(mode="after")
    def _match(self):
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _password(cls, v: str) -> str:
        return validate_password(v)


# ---------------------------------------------------------------------------
# User profile / admin
# ---------------------------------------------------------------------------


class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    email: Optional[str] = None
    bio: Optional[str] = None
    organization: Optional[str] = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: Optional[str]) -> Optional[str]:
        return validate_email(v) if v else v


class AdminUserUpdate(BaseModel):
    role: Optional[str] = Field(default=None, pattern=r"^(user|analyst|admin)$")
    active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Queries / pipeline
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    text: str = Field(min_length=6, max_length=2000)
    dataset_ids: Optional[list[str]] = None
    params: Optional[dict[str, Any]] = None


class QueryUnderstanding(BaseModel):
    query_text: str
    location: Optional[str] = None
    location_key: Optional[str] = None
    bbox: Optional[dict] = None
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    phenomenon: Optional[str] = None
    data_type: Optional[str] = None
    requested_analysis: Optional[str] = None
    analysis_type: str = "general"
    agent: str
    agent_confidence: float = 0.0
    confidence: float = 0.0
    explanation: list[str] = []
    raw_text: str = ""


class SaveAnalysisRequest(BaseModel):
    result_id: str
    name: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class MapPreferences(BaseModel):
    base_layer: str = "dark"
    show_labels: bool = True
    opacity: Optional[dict] = None


class NotificationPreferences(BaseModel):
    email_summary: bool = True
    job_updates: bool = True
    weekly_digest: bool = False
    # "New sign-in" security alert e-mails (login / MFA completion).
    security_alerts: bool = True


class UserSettingsUpdate(BaseModel):
    theme: Optional[str] = Field(default=None, pattern=r"^(dark|light)$")
    default_satellite_source: Optional[str] = None
    default_data_type: Optional[str] = None
    map_preferences: Optional[MapPreferences] = None
    notifications: Optional[NotificationPreferences] = None
    api_provider: Optional[str] = None
    api_key: Optional[str] = None
    language: Optional[str] = None


class ContactRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str
    subject: str = Field(max_length=200)
    message: str = Field(min_length=10, max_length=4000)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return validate_email(v)


# ---------------------------------------------------------------------------
# Historical change analysis (Date 1 vs Date 2)
# ---------------------------------------------------------------------------

CHANGE_MIN_DATE = date(1980, 1, 1)
CHANGE_TECHNIQUES = ("ndvi", "ndwi", "ndbi", "cva")
ChangeTechnique = Literal["ndvi", "ndwi", "ndbi", "cva"]


class ChangeLocation(BaseModel):
    """A place name/address OR GPS coordinates (latitude, longitude)."""

    text: Optional[str] = Field(
        default=None, max_length=200,
        description="Searchable place name / address, e.g. 'Mumbai' or 'Biển Hồ, Gia Lai'.",
    )
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _require_geometry(self):
        text = (self.text or "").strip()
        if not text and self.latitude is None:
            raise ValueError(
                "Provide a place name (text) or GPS coordinates (latitude/longitude)."
            )
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together.")
        return self


class ChangeAnalysisRequest(BaseModel):
    """Input contract for a historical change analysis job."""

    location: ChangeLocation
    date_1: date
    date_2: date
    query: str = Field(
        default="Show infrastructure change",
        min_length=3,
        max_length=1000,
        description="Custom prompt, e.g. 'Track new building construction'.",
    )
    techniques: Optional[list[ChangeTechnique]] = Field(
        default=None,
        description="Specific change-detection techniques. Defaults to query-driven selection.",
    )
    buffer_km: Optional[float] = Field(
        default=None, ge=0.1, le=50,
        description="AOI radius (km) when GPS coordinates are supplied.",
    )
    max_cells: Optional[int] = Field(
        default=None, ge=576, le=90000,
        description="Raster grid cell budget for the change engine (demo mode).",
    )

    @field_validator("query")
    @classmethod
    def _query_trim(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Query prompt is too short.")
        return v

    @model_validator(mode="after")
    def _dates_ordered(self):
        if self.date_2 <= self.date_1:
            raise ValueError("Date 2 must be after Date 1.")
        if self.date_1 < CHANGE_MIN_DATE:
            raise ValueError(f"Date 1 must be >= {CHANGE_MIN_DATE.isoformat()}.")
        return self