"""
app/core/security.py
────────────────────────────────────────────────────────────────────────────────
Security utilities: password hashing (PBKDF2-HMAC-SHA256), JWT token creation,
and OTP generation.

Password hashing is a one-way operation — it is impossible to decrypt a hashed
password back to its original value. Verification is done by hashing the
candidate and comparing the results using a timing-safe comparison.
"""
import asyncio
import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
_HASH_ITERATIONS = 260_000  # OWASP recommended iteration count for PBKDF2-SHA256
_SEPARATOR = ":"
_OTP_DIGITS = 6


# ── Password Hashing ───────────────────────────────────────────────────────────

def hash_password(plain_password: str) -> str:
    """Hash a plain-text password using PBKDF2-HMAC-SHA256 with a random salt.

    The returned string encodes the salt and hash together in the format:
        <hex_salt>:<hex_hash>
    This is irreversible — the original password cannot be recovered.
    """
    salt = os.urandom(32)
    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        plain_password.encode("utf-8"),
        salt,
        _HASH_ITERATIONS,
    )
    return salt.hex() + _SEPARATOR + hashed.hex()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a stored hash using a timing-safe comparison."""
    try:
        salt_hex, stored_hash_hex = hashed_password.split(_SEPARATOR, 1)
        salt = bytes.fromhex(salt_hex)
        candidate_hash = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt,
            _HASH_ITERATIONS,
        )
        return hmac.compare_digest(candidate_hash.hex(), stored_hash_hex)
    except (ValueError, AttributeError):
        return False


# ── OTP Generation ─────────────────────────────────────────────────────────────

def generate_otp() -> int:
    """Generate a cryptographically-random 6-digit OTP (100000–999999)."""
    return secrets.randbelow(900_000) + 100_000


def otp_expiry() -> datetime:
    """Return the UTC datetime when a freshly-generated OTP expires."""
    return datetime.now(tz=timezone.utc) + timedelta(minutes=settings.otp_expire_minutes)


# ── JWT Token ──────────────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    """Create a signed JWT access token.

    The token value is NOT logged anywhere — only the subject identity is logged
    for audit purposes. Callers must handle the returned token securely.
    """
    payload = data.copy()
    expire = datetime.now(tz=timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload["exp"] = expire
    payload["iat"] = datetime.now(tz=timezone.utc)

    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    logger.info("Access token issued for subject: %s", data.get("sub", "unknown"))
    return token


def create_refresh_token(data: dict) -> str:
    """Create a signed JWT refresh token.

    The refresh token has a longer expiration (7 days) and specifies the refresh scope.
    """
    payload = data.copy()
    expire = datetime.now(tz=timezone.utc) + timedelta(days=7)
    payload["exp"] = expire
    payload["iat"] = datetime.now(tz=timezone.utc)
    payload["scope"] = "refresh"

    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    logger.info("Refresh token issued for subject: %s", data.get("sub", "unknown"))
    return token


def create_password_reset_token(user_id: str, username: str) -> str:
    """Create a temporary password reset token valid for 10 minutes with password_reset scope."""
    payload = {
        "sub": str(user_id),
        "username": username,
        "scope": "password_reset"
    }
    expire = datetime.now(tz=timezone.utc) + timedelta(minutes=10)
    payload["exp"] = expire
    payload["iat"] = datetime.now(tz=timezone.utc)

    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    logger.info("Password reset token issued for subject: %s", user_id)
    return token


def verify_password_reset_token(token: str) -> dict:
    """Decode and validate a password reset JWT.

    Returns the decoded payload dict on success.
    Raises ValueError with a descriptive message if the token is expired,
    tampered, missing, or does not carry the 'password_reset' scope.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except Exception as exc:
        raise ValueError(f"Invalid or expired reset token: {exc}") from exc

    if payload.get("scope") != "password_reset":
        raise ValueError("Token does not carry password_reset scope.")

    return payload



async def hash_password_async(plain_password: str) -> str:
    """Run hash_password in a separate thread to avoid blocking the event loop."""
    return await asyncio.to_thread(hash_password, plain_password)


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    """Run verify_password in a separate thread to avoid blocking the event loop."""
    return await asyncio.to_thread(verify_password, plain_password, hashed_password)
