"""Pydantic schemas for the v1 auth & account-management vertical slice."""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DOMAIN_RE = re.compile(r"^(?!-)[a-zA-Z0-9-]{1,63}(?<!-)(\.[a-zA-Z0-9-]{1,63})+$")
OTP_RE = re.compile(r"^\d{6}$")

AccountType = Literal["student", "researcher", "gis_analyst", "organization"]


def validate_email(value: str) -> str:
    value = (value or "").strip().lower()
    if not EMAIL_RE.match(value):
        raise ValueError("Please provide a valid email address")
    return value


def validate_password(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters")
    return value


class StudentRegistration(BaseModel):
    account_type: Literal["student"] = "student"
    full_name: str = Field(min_length=2, max_length=80)
    email: str
    password: str
    confirm_password: str
    institution: str = Field(min_length=1, max_length=160)
    course: str = Field(min_length=1, max_length=160)
    year_of_study: int = Field(ge=1, le=10)

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


class ResearcherRegistration(BaseModel):
    account_type: Literal["researcher"] = "researcher"
    full_name: str = Field(min_length=2, max_length=80)
    email: str
    password: str
    confirm_password: str
    institution: str = Field(min_length=1, max_length=160)
    research_field: str = Field(min_length=1, max_length=200)
    orcid: Optional[str] = Field(default=None, max_length=32)
    profile_link: Optional[str] = Field(default=None, max_length=500)

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
class GisAnalystRegistration(BaseModel):
    account_type: Literal["gis_analyst"] = "gis_analyst"
    full_name: str = Field(min_length=2, max_length=80)
    email: str
    password: str
    confirm_password: str
    employer: str = Field(min_length=1, max_length=160)
    job_title: str = Field(min_length=1, max_length=160)
    years_experience: int = Field(ge=0, le=80)
    primary_tools: str = Field(min_length=1, max_length=300)

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


class OrganizationRegistration(BaseModel):
    account_type: Literal["organization"] = "organization"
    org_name: str = Field(min_length=2, max_length=120)
    org_type: Literal["government", "defense", "private"]
    official_domain: str = Field(min_length=4, max_length=253)
    admin_name: str = Field(min_length=2, max_length=80)
    admin_email: str
    team_size: int = Field(ge=1, le=1_000_000)
    intended_use: str = Field(min_length=4, max_length=2000)
    password: str
    confirm_password: str

    @field_validator("admin_email")
    @classmethod
    def _email(cls, v: str) -> str:
        return validate_email(v)

    @field_validator("official_domain")
    @classmethod
    def _domain(cls, v: str) -> str:
        v = (v or "").strip().lower().lstrip("www.")
        if not DOMAIN_RE.match(v):
            raise ValueError("Please provide a valid official domain (e.g. acme.gov)")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        return validate_password(v)

    @model_validator(mode="after")
    def _match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


RegistrationPayload = (
    StudentRegistration
    | ResearcherRegistration
    | GisAnalystRegistration
    | OrganizationRegistration
)


class VerifyEmailRequest(BaseModel):
    email: str
    code: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return validate_email(v)

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        v = v.strip()
        if not OTP_RE.match(v):
            raise ValueError("Verification code must be 6 digits")
        return v


class ResendVerificationRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return validate_email(v)


class UserLogin(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return validate_email(v)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
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
        if self.current_password == self.new_password:
            raise ValueError("New password must be different from current password")
        return self


class ChangePasswordVerifyRequest(BaseModel):
    password_change_id: str = Field(min_length=8)
    otp_code: str

    @field_validator("otp_code")
    @classmethod
    def _code(cls, v: str) -> str:
        v = v.strip()
        if not OTP_RE.match(v):
            raise ValueError("Verification code must be 6 digits")
        return v


class MfaChallengeRequest(BaseModel):
    mfa_token: str = Field(min_length=8)
    code: str = Field(min_length=3, max_length=12)


class MfaVerifyRequest(BaseModel):
    code: str = Field(min_length=3, max_length=12)


class InactivityTimeoutUpdate(BaseModel):
    inactivity_timeout_minutes: int = Field(ge=5, le=60)


class SessionOut(BaseModel):
    session_id: str
    device_label: str
    ip_address: str
    created_at: str
    last_seen_at: str
    expires_at: str
    current: bool = False