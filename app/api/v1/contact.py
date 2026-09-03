"""Public "Get in Touch" contact route for the landing page."""
from fastapi import APIRouter, Request

from app.core.limiter import limiter
from app.models.contact_models import ContactEnvelope, ContactRequest
from app.services.contact_service import contact_service

router = APIRouter(prefix="/contact", tags=["Contact"])


@router.post("", response_model=ContactEnvelope, summary="Submit a support query")
@limiter.limit("10/minute")
async def submit_contact_request(
    request: Request,
    payload: ContactRequest,
) -> ContactEnvelope:
    """Send the submitted name / email / topic / message to the support inbox.

    Intentionally public (no auth) — it backs the landing page "Get in Touch"
    form. Rate-limited separately from authenticated routes.
    """
    return await contact_service.submit_contact(payload)