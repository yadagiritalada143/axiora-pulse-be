"""
app/workers/background_jobs.py
────────────────────────────────────────────────────────────────────────────────
Lightweight in-process background job dispatcher.

No external broker (Celery/Redis/RQ/etc.) exists yet in this project, so jobs
run as detached asyncio tasks on the same event loop as the API. This keeps
the pattern already used for SMTP calls (asyncio.to_thread offloading) while
decoupling job execution from the request/response lifecycle: enqueue_email_job()
schedules work and returns immediately without awaiting delivery.

Delivery failures are retried with backoff and logged; they are never raised
back to the caller, so this is always safe to call right before an API
endpoint returns its response — email delivery failures must never fail the
request that triggered them.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict
from uuid import uuid4

from app.services import email_service

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = (2, 5)  # delay before attempt 2, delay before attempt 3

# asyncio only holds a weak reference to a task created via create_task(), so
# a strong reference must be kept somewhere or the task can be garbage
# collected mid-flight. This set is that reference; entries are removed by
# _on_task_done() once the task finishes.
_inflight_tasks: set = set()

_EMAIL_HANDLERS: Dict[str, Callable[..., Awaitable[Any]]] = {
    "registration_success": email_service.send_registration_success_email,
    "password_reset_success": email_service.send_password_reset_success_email,
}


@dataclass(frozen=True)
class EmailJob:
    job_type: str
    payload: Dict[str, Any]
    job_id: str = field(default_factory=lambda: uuid4().hex)


async def _run_email_job(job: EmailJob) -> None:
    handler = _EMAIL_HANDLERS.get(job.job_type)
    if handler is None:
        logger.error("Unknown email job type=%s (job_id=%s) — dropping.", job.job_type, job.job_id)
        return

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        logger.info(
            "Processing email job type=%s job_id=%s attempt=%s/%s",
            job.job_type, job.job_id, attempt, _MAX_ATTEMPTS,
        )
        result = None
        try:
            result = await handler(**job.payload)
        except Exception as exc:
            # Handlers (send_*_email) are designed to never raise, but a job
            # must never be able to crash silently regardless.
            logger.error(
                "Email job type=%s job_id=%s raised on attempt %s/%s: %s",
                job.job_type, job.job_id, attempt, _MAX_ATTEMPTS, exc,
            )

        if result is not None and getattr(result, "success", False):
            logger.info("Email job type=%s job_id=%s delivered successfully.", job.job_type, job.job_id)
            return

        error = getattr(result, "error", None) if result is not None else "handler raised an exception"
        if attempt < _MAX_ATTEMPTS:
            delay = _RETRY_BACKOFF_SECONDS[min(attempt - 1, len(_RETRY_BACKOFF_SECONDS) - 1)]
            logger.warning(
                "Email job type=%s job_id=%s failed attempt %s/%s (%s) — retrying in %ss.",
                job.job_type, job.job_id, attempt, _MAX_ATTEMPTS, error, delay,
            )
            await asyncio.sleep(delay)
        else:
            logger.error(
                "Email job type=%s job_id=%s failed permanently after %s attempts (%s). Job dropped.",
                job.job_type, job.job_id, _MAX_ATTEMPTS, error,
            )


def _on_task_done(task: "asyncio.Task") -> None:
    _inflight_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("Background email job task crashed unexpectedly: %s", exc, exc_info=exc)


def enqueue_email_job(job_type: str, **payload: Any) -> None:
    """Schedule a transactional email job to run in the background.

    Fire-and-forget: returns immediately without waiting for delivery.
    Failures are retried internally with backoff and logged; they never
    propagate to the caller.

    Args:
        job_type: one of the keys in _EMAIL_HANDLERS (e.g. "registration_success").
        **payload: forwarded as kwargs to the matching email_service.send_* function.
    """
    job = EmailJob(job_type=job_type, payload=payload)
    logger.info("Enqueued email job type=%s job_id=%s", job.job_type, job.job_id)
    task = asyncio.create_task(_run_email_job(job))
    _inflight_tasks.add(task)
    task.add_done_callback(_on_task_done)
