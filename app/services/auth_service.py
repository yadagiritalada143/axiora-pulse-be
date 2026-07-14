"""
app/services/auth_service.py
────────────────────────────────────────────────────────────────────────────────
Authentication service: user registration, login, and an in-memory user store.

NOTE: The in-memory store resets on each server restart. Replace with a
persistent database (e.g. PostgreSQL via SQLAlchemy) for production.
"""
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock

from fastapi import HTTPException, status

from app.core.security import create_access_token, hash_password, verify_password
from app.core.config import settings
from app.models.auth_models import (
    LoginSuccessResponse,
    UserRegisterRequest,
    UserLoginRequest,
    UserResponse,
)

logger = logging.getLogger(__name__)


# ── In-Memory User Store ───────────────────────────────────────────────────────

@dataclass
class _StoredUser:
    """Internal user record (never exposed in API responses)."""
    user_id: str
    email: str
    hashed_password: str
    registered_at: datetime


class _UserStore:
    """Thread-safe, in-memory store for registered users."""

    def __init__(self) -> None:
        self._store: dict[str, _StoredUser] = {}  # keyed by email
        self._lock = Lock()

    def add(self, user: _StoredUser) -> None:
        with self._lock:
            self._store[user.email] = user

    def get_by_email(self, email: str) -> _StoredUser | None:
        with self._lock:
            return self._store.get(email)

    def exists(self, email: str) -> bool:
        with self._lock:
            return email in self._store


# Module-level singleton — shared across all requests
user_store = _UserStore()


# ── Auth Service ───────────────────────────────────────────────────────────────

class AuthService:
    """Handles user registration and login operations."""

    def register(self, request: UserRegisterRequest) -> UserResponse:
        """Register a new user.

        Raises:
            HTTPException 409 if the email is already registered.
        """
        email = request.email.lower().strip()

        if user_store.exists(email):
            logger.warning("Registration attempt for already-registered email: %s", email)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            )

        stored = _StoredUser(
            user_id=str(uuid.uuid4()),
            email=email,
            hashed_password=hash_password(request.password),
            registered_at=datetime.now(tz=timezone.utc),
        )
        user_store.add(stored)
        logger.info("New user registered: %s (id=%s)", email, stored.user_id)

        return UserResponse(
            user_id=stored.user_id,
            email=stored.email,
            registered_at=stored.registered_at,
            message="Registration successful. You can now log in.",
        )

    def login(self, request: UserLoginRequest) -> tuple[str, LoginSuccessResponse]:
        """Authenticate a user and issue a JWT access token.

        Returns a tuple of (raw_token, LoginSuccessResponse). The raw token is
        intended to be set as an HttpOnly cookie by the router — it must never
        be placed in the response body.

        Raises:
            HTTPException 401 if credentials are invalid.
        """
        email = request.email.lower().strip()
        stored = user_store.get_by_email(email)

        # Deliberately generic error — do not reveal whether the email exists.
        if stored is None or not verify_password(request.password, stored.hashed_password):
            logger.warning("Failed login attempt for email: %s", email)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = create_access_token(data={"sub": stored.user_id, "email": stored.email})
        logger.info("Login successful for user: %s (id=%s)", email, stored.user_id)

        return token, LoginSuccessResponse(
            expires_in_minutes=settings.access_token_expire_minutes,
        )


# Module-level singleton
auth_service = AuthService()
