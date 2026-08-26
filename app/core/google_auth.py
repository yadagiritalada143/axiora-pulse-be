"""
app/core/google_auth.py
────────────────────────────────────────────────────────────────────────────────
Verification of Google Identity Services ID tokens.

The frontend obtains an ID token (a signed JWT) from Google's "Sign in with
Google" button and POSTs it to our backend. This module validates that token's
signature, issuer, audience, and expiry against Google's published public keys,
and returns the trusted identity claims.

We never trust identity fields sent directly by the client — only the claims
embedded in a token that verifies against Google's keys.
"""
import asyncio
import logging
import os

from dotenv import load_dotenv
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

load_dotenv()

logger = logging.getLogger(__name__)

_GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
_ACCEPTED_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}

# A single reusable transport; it caches Google's certs between calls.
_request_transport = google_requests.Request()


class GoogleTokenError(ValueError):
    """Raised when a Google ID token is missing, malformed, or fails verification."""


def _verify_sync(token: str) -> dict:
    if not _GOOGLE_CLIENT_ID:
        # Misconfiguration, not a client error — surface loudly in logs.
        logger.error("GOOGLE_CLIENT_ID is not configured; cannot verify Google ID tokens.")
        raise GoogleTokenError("Google sign-in is not configured on this server.")

    try:
        claims = google_id_token.verify_oauth2_token(
            token, _request_transport, _GOOGLE_CLIENT_ID
        )
    except ValueError as exc:
        # Covers bad signature, wrong audience, expired token, malformed JWT.
        logger.warning("Google ID token verification failed: %s", exc)
        raise GoogleTokenError("Invalid or expired Google credential.") from exc

    if claims.get("iss") not in _ACCEPTED_ISSUERS:
        logger.warning("Google ID token has unexpected issuer: %s", claims.get("iss"))
        raise GoogleTokenError("Invalid Google credential issuer.")

    if not claims.get("email"):
        raise GoogleTokenError("Google credential did not include an email address.")

    return claims


async def verify_google_id_token(token: str) -> dict:
    """Verify a Google ID token off the event loop and return its trusted claims.

    Returns the decoded claim dict, which includes at least: ``sub``, ``email``,
    ``email_verified``, and (when the profile scope is granted) ``given_name``,
    ``family_name``, ``name``, and ``picture``.

    Raises:
        GoogleTokenError: if the token is absent or fails verification.
    """
    if not token or not token.strip():
        raise GoogleTokenError("Missing Google credential.")
    return await asyncio.to_thread(_verify_sync, token.strip())
