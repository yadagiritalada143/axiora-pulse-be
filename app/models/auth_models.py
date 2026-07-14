"""
app/models/auth_models.py
────────────────────────────────────────────────────────────────────────────────
Pydantic models for authentication endpoints.

Validation rules (zero custom regex used):
  • Email  → validated by Pydantic's built-in EmailStr (uses the email-validator
             library under the hood).
  • Password → validated using Python's built-in str methods:
             .isupper(), .islower(), .isdigit(), .isprintable(), and
             the built-in any() function.
"""
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


# ── Request Models ─────────────────────────────────────────────────────────────

class UserRegisterRequest(BaseModel):
    """Payload for POST /api/v1/auth/register."""
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        """Enforce password policy using standard Python str methods only."""
        errors = []

        if len(value) < 8:
            errors.append("at least 8 characters")

        if not any(c.isupper() for c in value):
            errors.append("at least one uppercase letter")

        if not any(c.islower() for c in value):
            errors.append("at least one lowercase letter")

        if not any(c.isdigit() for c in value):
            errors.append("at least one digit")

        _special = set("!@#$%^&*()_+-=[]{}|;':\",./<>?")
        if not any(c in _special for c in value):
            errors.append("at least one special character (!@#$%^&*...)")

        if errors:
            raise ValueError("Password must contain: " + ", ".join(errors))

        return value


class UserLoginRequest(BaseModel):
    """Payload for POST /api/v1/auth/login."""
    email: EmailStr
    password: str


# ── Response Models ────────────────────────────────────────────────────────────

class LoginSuccessResponse(BaseModel):
    """Returned on successful login. Token is delivered via HttpOnly cookie only."""
    message: str = "Login successful."
    token_type: str = "bearer"
    expires_in_minutes: int


class UserResponse(BaseModel):
    """Returned on successful registration."""
    user_id: str
    email: str
    registered_at: datetime
    message: str
