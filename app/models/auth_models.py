"""
app/models/auth_models.py
────────────────────────────────────────────────────────────────────────────────
Pydantic request/response models for all authentication endpoints.

Endpoints covered:
  POST /register    → UserRegisterRequest  → RegisterResponse
  POST /verifyOTP   → VerifyOTPRequest     → VerifyOTPResponse
  POST /resendOTP   → ResendOTPRequest     → RegisterResponse
  POST /login       → UserLoginRequest     → LoginSuccessResponse
"""
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, field_validator


# ── Request Models ─────────────────────────────────────────────────────────────

class UserRegisterRequest(BaseModel):
    """Payload for POST /api/v1/auth/register."""
    username: EmailStr          # email address used as the unique username
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
    username: EmailStr
    password: str


class VerifyOTPRequest(BaseModel):
    """Payload for POST /api/v1/auth/verifyOTP."""
    id: int
    otp: int
    flow: Literal["register"]   # extensible for future flows (e.g. "login")


class ResendOTPRequest(BaseModel):
    """Payload for POST /api/v1/auth/resendOTP."""
    id: int
    flow: Literal["register"]


# ── Response Models ────────────────────────────────────────────────────────────

class RegisterResponse(BaseModel):
    """Returned after successful registration or OTP resend."""
    userid: int
    username: str
    registerMFA: bool


class VerifyOTPResponse(BaseModel):
    """Returned after OTP verification attempt."""
    status: str                     # "success" | "failed"
    message: str
    jwt: Optional[str] = None       # Present only on success


class LoginSuccessResponse(BaseModel):
    """Returned on successful login."""
    status: str = "success"
    message: str = "Login successful."
    jwt: str
    token_type: str = "bearer"
    expires_in_minutes: int


class ForgotPasswordRequest(BaseModel):
    """Payload for POST /api/v1/auth/forgot-password/request."""
    emailOrMobile: str


class ForgotPasswordResponse(BaseModel):
    """Returned after forgot password reset request is processed."""
    status: str = "success"
    message: str = "Password reset code has been sent."


class ForgotPasswordVerifyRequest(BaseModel):
    """Payload for POST /api/v1/auth/forgot-password/verify."""
    emailOrMobile: str
    code: int


class ForgotPasswordVerifyResponse(BaseModel):
    """Returned after successful password reset verification."""
    status: str = "success"
    message: str = "Code verified successfully."
    reset_token: str


class ForgotPasswordResetRequest(BaseModel):
    """Payload for POST /api/v1/auth/forgot-password/reset."""
    reset_token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, value: str) -> str:
        """Enforce the same password policy as registration."""
        errors = []

        if len(value) < 8:
            errors.append("at least 8 characters")

        if not any(c.isupper() for c in value):
            errors.append("at least one uppercase letter")

        if not any(c.islower() for c in value):
            errors.append("at least one lowercase letter")

        if not any(c.isdigit() for c in value):
            errors.append("at least one digit")

        _special = set("!@#$%^&*()_+-=[]{}|;':\",.//<>?")
        if not any(c in _special for c in value):
            errors.append("at least one special character (!@#$%^&*...)")

        if errors:
            raise ValueError("Password must contain: " + ", ".join(errors))

        return value


class ForgotPasswordResetResponse(BaseModel):
    """Returned after a successful password reset."""
    status: str = "success"
    message: str = "Password has been reset successfully. Please log in with your new password."


class ChangePasswordRequest(BaseModel):
    """Payload for POST /api/v1/auth/change-password."""
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, value: str) -> str:
        """Enforce standard password security requirements."""
        errors = []

        if len(value) < 8:
            errors.append("at least 8 characters")

        if not any(c.isupper() for c in value):
            errors.append("at least one uppercase letter")

        if not any(c.islower() for c in value):
            errors.append("at least one lowercase letter")

        if not any(c.isdigit() for c in value):
            errors.append("at least one digit")

        _special = set("!@#$%^&*()_+-=[]{}|;':\",.//<>?")
        if not any(c in _special for c in value):
            errors.append("at least one special character (!@#$%^&*...)")

        if errors:
            raise ValueError("Password must contain: " + ", ".join(errors))

        return value


class ChangePasswordResponse(BaseModel):
    """Returned after a successful password change."""
    status: str = "success"
    message: str = "Password changed successfully. Your other sessions have been logged out."


class LoginOTPResponse(BaseModel):
    """Returned after credentials are validated and login OTP is dispatched."""
    status: str = "success"
    message: str = "A login verification code has been sent."


class VerifyLoginRequest(BaseModel):
    """Payload for POST /api/v1/auth/verify-login."""
    emailOrMobile: str
    otp: int


class VerifyLoginResponse(BaseModel):
    """Returned on successful login verification."""
    status: str = "success"
    message: str = "Login successful."
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in_minutes: int





