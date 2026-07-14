"""
app/api/v1/auth.py
────────────────────────────────────────────────────────────────────────────────
Authentication router: register and login endpoints.

Token delivery strategy:
  The JWT access token is set as an HttpOnly, Secure, SameSite=Lax cookie.
  It is never included in the response body — this prevents it from being
  read by JavaScript or exposed in API response logs.
"""
from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.models.auth_models import (
    LoginSuccessResponse,
    UserRegisterRequest,
    UserLoginRequest,
    UserResponse,
)
from app.services.auth_service import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])

_COOKIE_NAME = "access_token"


# ── Register ───────────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description=(
        "Creates a new user account using email and password. "
        "The password is hashed with PBKDF2-HMAC-SHA256 and can never be decrypted. "
        "Returns the created user profile — no token is issued at registration."
    ),
)
async def register(request: UserRegisterRequest) -> UserResponse:
    return auth_service.register(request)


# ── Login ──────────────────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=LoginSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Login and obtain an access token",
    description=(
        "Authenticates a user with email and password. "
        "On success, the JWT token is set as an HttpOnly cookie — "
        "it is NOT returned in the response body. "
        "The browser/client will send it automatically on subsequent requests."
    ),
)
async def login(request: UserLoginRequest, response: Response) -> LoginSuccessResponse:
    token, result = auth_service.login(request)

    # Set the token as an HttpOnly cookie — invisible to JavaScript and
    # absent from the JSON response body.
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,           # Blocks JavaScript access
        secure=False,            # Set to True in production (requires HTTPS)
        samesite="lax",          # Protects against CSRF attacks
        max_age=settings.access_token_expire_minutes * 60,
    )

    return result
