"""
app/api/v1/auth.py
────────────────────────────────────────────────────────────────────────────────
Authentication router: register, verifyOTP, resendOTP, and login endpoints.

Token strategy:
  - JWT is returned in the response body on verifyOTP success and login.
  - This allows SPA / mobile clients to store and send it as a Bearer token.
"""
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import limiter
from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import User
from app.models.auth_models import (
    AdminLoginResponse,
    GoogleAuthRequest,
    GoogleAuthResponse,
    LoginSuccessResponse,
    RegisterResponse,
    ResendOTPRequest,
    UserLoginRequest,
    UserRegisterRequest,
    VerifyOTPRequest,
    VerifyOTPResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ForgotPasswordVerifyRequest,
    ForgotPasswordVerifyResponse,
    ForgotPasswordResetRequest,
    ForgotPasswordResetResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    LoginOTPResponse,
    VerifyLoginRequest,
    VerifyLoginResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    LogoutResponse,
)
from app.services.auth_service import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/refresh", response_model=RefreshTokenResponse, summary="Rotate a refresh token")
@limiter.limit("30/minute")
async def refresh_token(
    request: Request,
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> RefreshTokenResponse:
    return await auth_service.refresh(payload, db)


@router.post("/logout", response_model=LogoutResponse, summary="Log out the current user")
@limiter.limit("30/minute")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LogoutResponse:
    return await auth_service.logout(current_user, db)


# ── Register ───────────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description=(
        "Creates a new user account. "
        "The password is hashed with PBKDF2-HMAC-SHA256. "
        "A 6-digit OTP is generated and sent to the provided email. "
        "Returns the user record — MFA is not yet complete at this stage."
    ),
)
@limiter.limit("5/minute")
async def register(
    request: Request,
    payload: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    return await auth_service.register(payload, db)


# ── Verify OTP ─────────────────────────────────────────────────────────────────

@router.post(
    "/verifyOTP",
    response_model=VerifyOTPResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify OTP and complete MFA",
    description=(
        "Validates the 6-digit OTP submitted by the user for either 'register' or 'login' flows. "
        "Supports user identification via 'id' (int/str) or 'emailOrMobile' (str). "
        "On success: completes MFA and returns signed access and refresh tokens. "
        "On failure: returns status='failed' with a descriptive message."
    ),
)
@limiter.limit("5/minute")
async def verify_otp(
    request: Request,
    payload: VerifyOTPRequest,
    db: AsyncSession = Depends(get_db),
) -> VerifyOTPResponse:
    return await auth_service.verify_otp(payload, db)


# ── Resend OTP ─────────────────────────────────────────────────────────────────

@router.post(
    "/resendOTP",
    response_model=RegisterResponse,
    status_code=status.HTTP_200_OK,
    summary="Resend OTP",
    description=(
        "Generates a new 6-digit OTP and sends it via email/SMS. "
        "Supports both 'register' and 'login' flows via the 'flow' parameter ('register' | 'login'). "
        "Accepts user identification via 'id' (int/str) or 'emailOrMobile'/'email' (str). "
        "Invalidates the previous OTP and dispatches a fresh code."
    ),
)
@limiter.limit("3/minute")
async def resend_otp(
    request: Request,
    payload: ResendOTPRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    return await auth_service.resend_otp(payload, db)


# ── Login ──────────────────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=LoginSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Login and obtain access/refresh tokens",
    description=(
        "Authenticates a user with username (email) and password. "
        "Requires that registration OTP verification has been completed (registerMFA=True). "
        "Returns signed JWT access and refresh token pair in the response body."
    ),
)
@limiter.limit("5/minute")
async def login(
    request: Request,
    payload: UserLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginSuccessResponse:
    return await auth_service.login(payload, db)



# ── Verify Login ───────────────────────────────────────────────────────────────

@router.post(
    "/verify-login",
    response_model=VerifyLoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify login OTP and obtain access/refresh tokens",
    description=(
        "Accepts user identifier (emailOrMobile) and the 6-digit login OTP. "
        "On success, invalidates the OTP and returns a signed JWT access/refresh token pair."
    ),
)
@limiter.limit("5/minute")
async def verify_login(
    request: Request,
    payload: VerifyLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> VerifyLoginResponse:
    return await auth_service.verify_login(payload, db)


# ── Google Sign-In ──────────────────────────────────────────────────────────

@router.post(
    "/google",
    response_model=GoogleAuthResponse,
    status_code=status.HTTP_200_OK,
    summary="Sign in or register with Google",
    description=(
        "Accepts a Google Identity Services ID token ('credential'). "
        "Verifies it against Google's public keys, then logs the user in — "
        "linking to an existing account by email or provisioning a new one. "
        "No OTP is required since Google has already verified the email. "
        "Returns a signed access/refresh token pair plus 'is_new_user'."
    ),
)
@limiter.limit("10/minute")
async def google_sign_in(
    request: Request,
    payload: GoogleAuthRequest,
    db: AsyncSession = Depends(get_db),
) -> GoogleAuthResponse:
    return await auth_service.google_sign_in(payload, db)


# ── Admin Login ───────────────────────────────────────────────────────────────

@router.post(
    "/admin/login",
    response_model=AdminLoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Admin login endpoint",
    description=(
        "Authenticates admin with email and password. "
        "Returns access/refresh tokens, role='admin', and permitted actions=['dashboard']."
    ),
)
@limiter.limit("5/minute")
async def admin_login(
    request: Request,
    payload: UserLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> AdminLoginResponse:
    return await auth_service.admin_login(payload, db)




# ── Forgot Password Request ───────────────────────────────────────────────────

@router.post(
    "/forgot-password/request",
    response_model=ForgotPasswordResponse,
    status_code=status.HTTP_200_OK,
    summary="Request a password reset code",
    description=(
        "Accepts user identifier (emailOrMobile). "
        "Generates a 6-digit OTP code if user exists and dispatches it. "
        "Returns a generic success response to prevent user enumeration."
    ),
)
@limiter.limit("5/minute")
async def forgot_password_request(
    request: Request,
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> ForgotPasswordResponse:
    return await auth_service.forgot_password_request(payload, db)


# ── Forgot Password Verify ────────────────────────────────────────────────────

@router.post(
    "/forgot-password/verify",
    response_model=ForgotPasswordVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify password reset code",
    description=(
        "Accepts user identifier (emailOrMobile) and the reset code. "
        "Validates code against database. On success, returns a secure 10-minute temporary reset token."
    ),
)
@limiter.limit("5/minute")
async def forgot_password_verify(
    request: Request,
    payload: ForgotPasswordVerifyRequest,
    db: AsyncSession = Depends(get_db),
) -> ForgotPasswordVerifyResponse:
    return await auth_service.forgot_password_verify(payload, db)


# ── Forgot Password Reset ─────────────────────────────────────────────────────

@router.post(
    "/forgot-password/reset",
    response_model=ForgotPasswordResetResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset password using temporary token",
    description=(
        "Accepts the temporary reset token and the new password. "
        "Validates the token, hashes the new password, updates PostgreSQL, "
        "stamps password_changed_at to revoke all prior access tokens, "
        "and returns a fresh access/refresh token pair for immediate login."
    ),
)
@limiter.limit("3/minute")
async def forgot_password_reset(
    request: Request,
    payload: ForgotPasswordResetRequest,
    db: AsyncSession = Depends(get_db),
) -> ForgotPasswordResetResponse:
    return await auth_service.forgot_password_reset(payload, db)


# ── Change Password (Authenticated) ───────────────────────────────────────────

@router.post(
    "/change-password",
    response_model=ChangePasswordResponse,
    status_code=status.HTTP_200_OK,
    summary="Change password for authenticated user",
    description=(
        "Requires authentication via standard JWT Bearer token. "
        "Verifies the current password, updates it in PostgreSQL, "
        "and updates password_changed_at to revoke all other access tokens."
    ),
)
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChangePasswordResponse:
    return await auth_service.change_password(current_user, payload, db)




