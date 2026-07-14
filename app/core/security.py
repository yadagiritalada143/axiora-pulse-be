"""
app/core/security.py
────────────────────────────────────────────────────────────────────────────────
Security utilities: password hashing (PBKDF2-HMAC-SHA256) and JWT token creation.

Password hashing is a one-way operation — it is impossible to decrypt a hashed
password back to its original value. Verification is done by hashing the
candidate and comparing the results using a timing-safe comparison.
"""
import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
_HASH_ITERATIONS = 260_000  # OWASP recommended iteration count for PBKDF2-SHA256
_SEPARATOR = ":"


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
