"""
app/services/contact_service.py
────────────────────────────────────────────────────────────────────────────────
Service layer for the public "Get in Touch" contact form.

Submissions are forwarded to the support inbox as a background email job so SMTP
delivery never blocks or fails the request (same pattern as the transactional
auth emails).
"""
import logging

from app.models.contact_models import ContactEnvelope, ContactRequest
from app.workers.background_jobs import enqueue_email_job

logger = logging.getLogger(__name__)


class ContactService:
    """Handles website contact-form submissions."""

    async def submit_contact(self, payload: ContactRequest) -> ContactEnvelope:
        """Forward a validated contact submission to the support inbox.

        Fire-and-forget email dispatch: enqueue_email_job() schedules the SMTP
        send as a background task and never propagates delivery failures to the
        caller, so this never blocks or fails the HTTP request.
        """
        enqueue_email_job(
            "contact_support",
            name=payload.name,
            email=str(payload.email).lower().strip(),
            topic=payload.topic,
            message=payload.message,
        )
        logger.info("Contact request submitted by %s (topic=%s)", payload.email, payload.topic)
        return ContactEnvelope(
            success=True,
            message="Thanks for getting in touch! Our team will get back to you soon.",
        )


contact_service = ContactService()