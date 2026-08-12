import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services.email_service import OTPResult
from app.workers import background_jobs


@pytest.fixture(autouse=True)
def _clear_inflight_tasks():
    background_jobs._inflight_tasks.clear()
    yield
    background_jobs._inflight_tasks.clear()


@pytest.mark.asyncio
async def test_run_email_job_success_on_first_attempt():
    handler = AsyncMock(return_value=OTPResult(success=True, channel="email"))
    with patch.dict(background_jobs._EMAIL_HANDLERS, {"registration_success": handler}):
        job = background_jobs.EmailJob(job_type="registration_success", payload={"to_email": "a@b.com"})
        await background_jobs._run_email_job(job)
    handler.assert_awaited_once_with(to_email="a@b.com")


@pytest.mark.asyncio
async def test_run_email_job_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(background_jobs, "_RETRY_BACKOFF_SECONDS", (0, 0))
    handler = AsyncMock(
        side_effect=[
            OTPResult(success=False, channel="email", error="temporary SMTP outage"),
            OTPResult(success=True, channel="email"),
        ]
    )
    with patch.dict(background_jobs._EMAIL_HANDLERS, {"password_reset_success": handler}):
        job = background_jobs.EmailJob(job_type="password_reset_success", payload={"to_email": "a@b.com"})
        await background_jobs._run_email_job(job)
    assert handler.await_count == 2


@pytest.mark.asyncio
async def test_run_email_job_gives_up_after_max_attempts(monkeypatch, caplog):
    monkeypatch.setattr(background_jobs, "_RETRY_BACKOFF_SECONDS", (0, 0))
    handler = AsyncMock(return_value=OTPResult(success=False, channel="email", error="permanent failure"))
    with patch.dict(background_jobs._EMAIL_HANDLERS, {"registration_success": handler}):
        job = background_jobs.EmailJob(job_type="registration_success", payload={"to_email": "a@b.com"})
        with caplog.at_level("ERROR"):
            await background_jobs._run_email_job(job)
    assert handler.await_count == background_jobs._MAX_ATTEMPTS
    assert any("failed permanently" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_run_email_job_survives_handler_exception(monkeypatch):
    monkeypatch.setattr(background_jobs, "_RETRY_BACKOFF_SECONDS", (0, 0))
    handler = AsyncMock(side_effect=RuntimeError("boom"))
    with patch.dict(background_jobs._EMAIL_HANDLERS, {"registration_success": handler}):
        job = background_jobs.EmailJob(job_type="registration_success", payload={"to_email": "a@b.com"})
        # Must not propagate even though the handler always raises.
        await background_jobs._run_email_job(job)
    assert handler.await_count == background_jobs._MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_run_email_job_drops_unknown_job_type(caplog):
    job = background_jobs.EmailJob(job_type="not_a_real_type", payload={})
    with caplog.at_level("ERROR"):
        await background_jobs._run_email_job(job)
    assert any("Unknown email job type" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_enqueue_email_job_is_fire_and_forget_and_never_raises():
    handler = AsyncMock(return_value=OTPResult(success=True, channel="email"))
    with patch.dict(background_jobs._EMAIL_HANDLERS, {"registration_success": handler}):
        background_jobs.enqueue_email_job("registration_success", to_email="a@b.com")
        # Returns immediately without awaiting delivery — the task is merely scheduled.
        assert len(background_jobs._inflight_tasks) == 1
        await asyncio.gather(*background_jobs._inflight_tasks)
    handler.assert_awaited_once_with(to_email="a@b.com")
    # The done-callback removes the task from the tracking set once complete.
    assert len(background_jobs._inflight_tasks) == 0
