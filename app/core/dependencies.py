"""
app/core/dependencies.py
────────────────────────────────────────────────────────────────────────────────
Reusable FastAPI dependencies for protected routes.

get_current_user:
  - Extracts the Bearer token from the Authorization header.
  - Decodes and validates the JWT (signature, expiry, algorithm).
  - Checks that the token was issued AFTER the user's last password change
    (password_changed_at) — this provides stateless token revocation
    without a token blacklist or session table.
  - Returns the User ORM object for use in route handlers.

Usage:
    from app.core.dependencies import get_current_user
    from app.db.models import User

    @router.get("/me")
    async def get_me(current_user: User = Depends(get_current_user)):
        return {"id": current_user.id, "username": current_user.username}
"""
import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User

load_dotenv()

_JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
_JWT_ALGORITHM  = os.getenv("JWT_ALGORITHM")

logger = logging.getLogger(__name__)

# HTTPBearer scheme for Swagger UI — displays `bearerAuth (http, Bearer)` dialog
http_bearer = HTTPBearer(scheme_name="bearerAuth")


async def get_current_user(
    auth_credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Decode the access token and return the authenticated User.

    Raises HTTP 401 if:
      - The token is missing, malformed, or expired.
      - The token was issued before the user's last password change
        (i.e., the user has since reset their password — token is revoked).
      - The user no longer exists in the database.
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # ── Decode token ───────────────────────────────────────────────────────────
    token = auth_credentials.credentials
    try:
        payload = jwt.decode(
            token,
            _JWT_SECRET_KEY,
            algorithms=[_JWT_ALGORITHM],
        )
    except JWTError as exc:
        logger.warning("JWT decode failed: %s", exc)
        raise credentials_exc

    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise credentials_exc

    # Reject password-reset scoped tokens — they must not grant access.
    if payload.get("scope") == "password_reset":
        raise credentials_exc

    # ── Load user ──────────────────────────────────────────────────────────────
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exc

    # ── Revocation check (password_changed_at) ─────────────────────────────────
    # If the user changed their password, any token issued before that moment
    # is considered revoked. `iat` is the "issued at" claim (seconds since epoch).
    password_changed_at = user.password_changed_at
    if password_changed_at is not None:
        iat = payload.get("iat")
        if iat is None:
            raise credentials_exc

        # Ensure timezone-aware comparison
        if password_changed_at.tzinfo is None:
            password_changed_at = password_changed_at.replace(tzinfo=timezone.utc)

        token_issued_at = datetime.fromtimestamp(iat, tz=timezone.utc)
        if token_issued_at < password_changed_at:
            logger.warning(
                "Revoked token used by user id=%s (issued before password change).", user.id
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Your password was recently changed. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return user
