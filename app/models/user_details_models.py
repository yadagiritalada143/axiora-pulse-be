"""
app/models/user_details_models.py
────────────────────────────────────────────────────────────────────────────────
Pydantic request/response models for the extended user-profile ("user_details") API.

Endpoints covered:
  POST /api/v1/user-details        → CreateUserDetailsRequest → UserDetailsResponse
  GET  /api/v1/user-details        → UserDetailsResponse
  PUT  /api/v1/user-details        → UpdateUserDetailsRequest → UserDetailsResponse
"""
import re
from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

# Indian mobile number: optional +91/91 prefix, then a 10-digit number starting 6-9.
_MOBILE_PATTERN = re.compile(r"^(?:\+?91)?([6-9]\d{9})$")


def _validate_mobile_number(value: str) -> str:
    digits = value.strip().replace(" ", "").replace("-", "")
    match = _MOBILE_PATTERN.match(digits)
    if not match:
        raise ValueError("Mobile number must be a valid 10-digit Indian number (optionally prefixed with +91).")
    return match.group(1)


def _blank_to_none(value: str | None) -> str | None:
    """Store NULL instead of an empty/whitespace-only string for optional text fields."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


# ── Request Models ─────────────────────────────────────────────────────────────

class CreateUserDetailsRequest(BaseModel):
    """Payload for POST /api/v1/user-details."""
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: Optional[EmailStr] = Field(None, description="Defaults to the account's login email (users.username) when omitted")
    mobile_number: str = Field(..., description="10-digit Indian mobile number, optionally prefixed with +91")
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=20)
    nationality: Optional[str] = Field(None, max_length=100)
    communication_preferences: List[Literal["Email", "SMS", "Push"]] = Field(default_factory=list)

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile_number(cls, value: str) -> str:
        return _validate_mobile_number(value)

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth(cls, value: date | None) -> date | None:
        if value is not None and value >= date.today():
            raise ValueError("Date of birth must be in the past.")
        return value

    @field_validator("gender", "nationality")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        return _blank_to_none(value)


class UpdateUserDetailsRequest(BaseModel):
    """Payload for PUT /api/v1/user-details. Only provided fields are updated."""
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    mobile_number: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=20)
    nationality: Optional[str] = Field(None, max_length=100)
    communication_preferences: Optional[List[Literal["Email", "SMS", "Push"]]] = None

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile_number(cls, value: str | None) -> str | None:
        return _validate_mobile_number(value) if value is not None else None

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth(cls, value: date | None) -> date | None:
        if value is not None and value >= date.today():
            raise ValueError("Date of birth must be in the past.")
        return value

    @field_validator("gender", "nationality")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        return _blank_to_none(value)


class SetProfileStatusRequest(BaseModel):
    """Payload for PATCH /api/v1/admin/user-details/{user_id}/status."""
    profile_status: Literal["Active", "Inactive", "Suspended"]


# ── Response Models ────────────────────────────────────────────────────────────

class UserDetailsResponse(BaseModel):
    """Returned for a user's extended profile."""
    profile_id: str
    user_id: int
    first_name: str
    last_name: str
    email: str
    mobile_number: str
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    profile_status: str
    nationality: Optional[str] = None
    communication_preferences: List[str] = Field(default_factory=list)
    last_login_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
