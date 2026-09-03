"""Tests for the public "Get in Touch" contact endpoint."""
from unittest.mock import patch

import pytest

from app.services.email_service import _build_contact_email, _CONTACT_RECIPIENT_EMAIL


@pytest.fixture(autouse=True)
def _stub_contact_email_job():
    """Prevent the contact endpoint from spawning a real background SMTP task."""
    with patch("app.services.contact_service.enqueue_email_job") as mock_enqueue:
        yield mock_enqueue


async def test_contact_submission_success(client, _stub_contact_email_job):
    payload = {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "topic": "Billing question",
        "message": "How do I upgrade my plan to the pro tier?",
    }
    resp = await client.post("/api/v1/contact", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "get back to you" in body["message"]

    _stub_contact_email_job.assert_called_once_with(
        "contact_support",
        name="Ada Lovelace",
        email="ada@example.com",
        topic="Billing question",
        message="How do I upgrade my plan to the pro tier?",
    )


async def test_contact_submission_enqueues_job_with_run_email_job(client, _stub_contact_email_job):
    """The enqueued handler is wired to the real SMTP sender in background_jobs."""
    from app.workers import background_jobs

    assert "contact_support" in background_jobs._EMAIL_HANDLERS
    handler = background_jobs._EMAIL_HANDLERS["contact_support"]
    assert handler.__name__ == "send_contact_email"


async def test_contact_submission_rejects_blank_fields(client, _stub_contact_email_job):
    payload = {
        "name": "   ",
        "email": "not-an-email",
        "topic": "Billing",
        "message": "",
    }
    resp = await client.post("/api/v1/contact", json=payload)

    assert resp.status_code == 422
    _stub_contact_email_job.assert_not_called()


async def test_contact_submission_rejects_missing_field(client, _stub_contact_email_job):
    payload = {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "topic": "Billing question",
    }
    resp = await client.post("/api/v1/contact", json=payload)

    assert resp.status_code == 422
    _stub_contact_email_job.assert_not_called()


def test_build_contact_email_targets_support_inbox_and_sets_reply_to():
    msg = _build_contact_email(
        name="Ada <Lovelace>",
        email="ada@example.com",
        topic='Billing "question"',
        message="Line one\nLine two",
    )
    assert msg["To"] == _CONTACT_RECIPIENT_EMAIL
    assert msg["Reply-To"] == "ada@example.com"
    assert "New Contact Request: Billing" in msg["Subject"]
    # User content must be HTML-escaped inside the HTML body.
    html_part = {p.get_content_type(): p for p in msg.walk() if p.get_content_type() == "text/html"}
    html_body = html_part["text/html"].get_payload(decode=True).decode("utf-8")
    assert "Ada &lt;Lovelace&gt;" in html_body