"""
app/models/contact_models.py
────────────────────────────────────────────────────────────────────────────────
Pydantic request/response models for the public "Get in Touch" contact endpoint.

Endpoint covered:
  POST /api/v1/contact → ContactRequest → ContactEnvelope

The landing-page contact form collects name, email address, topic and message.
Submissions are forwarded to the support inbox via email_service; the envelope
keeps the standard `{ success, message }` shape the SPA services expect.
"""
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Request Models ─────────────────────────────────────────────────────────────

class ContactRequest(BaseModel):
    """Payload for POST /api/v1/contact."""
    name: str = Field(..., min_length=1, max_length=120, description="Contact person's full name")
    email: EmailStr = Field(..., description="Contact person's email address (for replies)")
    topic: str = Field(..., min_length=1, max_length=120, description="Subject/topic of the query")
    message: str = Field(..., min_length=1, max_length=5000, description="Query details")

    @field_validator("name", "topic", "message")
    @classmethod
    def strip_and_require_non_blank(cls, value: str) -> str:
        """Trim surrounding whitespace and reject all-whitespace values."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("This field cannot be blank.")
        return stripped


# ── Envelopes ──────────────────────────────────────────────────────────────────

class ContactEnvelope(BaseModel):
    success: bool = True
    message: Optional[str] = None