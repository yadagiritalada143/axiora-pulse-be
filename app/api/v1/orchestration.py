"""
Orchestration API Routes  —  /api/v1/orchestration
──────────────────────────────────────────────────────────────────────────────
POST /api/v1/orchestration/run
    → Start a full orchestration run

GET  /api/v1/orchestration/{run_id}/research-traces
    → Fetch captured research queries & sources (JSON polling)

GET  /api/v1/orchestration/{run_id}/research-stream
    → Server-Sent Events stream of live research queries & sources

Health checks are handled globally at GET /health (see main.py).
"""
import json
import logging

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.models.orchestration_models import (
    OrchestrationRequest,
    OrchestrationResponse,
    ResearchTraceResponse,
)
from app.orchestration.orchestrator import orchestrator
from app.services.research_trace_service import research_trace_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orchestration", tags=["Orchestration"])


# ── POST /run ──────────────────────────────────────────────────────────────────

@router.post(
    "/run",
    response_model=OrchestrationResponse,
    summary="Run idea validation (or other workflow)",
    description=(
        "Triggers an orchestration run. In Phase 1 the only supported workflow is "
        "`idea_validation`. Pass your idea details in the request body."
    ),
)
async def run_orchestration(request: OrchestrationRequest) -> OrchestrationResponse:
    logger.info(
        f"[API] POST /orchestration/run | workflow={request.workflow_type} | "
        f"idea='{request.idea.idea_title}'"
    )

    try:
        response = await orchestrator.run(request)
        return response
    except Exception as e:
        logger.error(f"[API] Unhandled error in /orchestration/run: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again.",
        )


# ── GET /{run_id}/research-traces ─────────────────────────────────────────────

@router.get(
    "/{run_id}/research-traces",
    response_model=ResearchTraceResponse,
    summary="Get research queries and sources for a run (polling)",
    description=(
        "Returns all research queries issued by agents and all web sources retrieved "
        "during the orchestration run identified by `run_id`. "
        "Poll this endpoint while `is_active` is `true` to track live progress."
    ),
)
async def get_research_traces(run_id: str) -> ResearchTraceResponse:
    logger.info(f"[API] GET /orchestration/{run_id}/research-traces")
    return research_trace_service.get_traces(run_id)


# ── GET /{run_id}/research-stream ─────────────────────────────────────────────

@router.get(
    "/{run_id}/research-stream",
    summary="Live SSE stream of research queries and sources",
    description=(
        "Streams real-time Server-Sent Events (SSE) for research queries and web "
        "sources as agents execute. Connect via EventSource or curl. "
        "The stream closes automatically when the orchestration run completes."
    ),
)
async def research_stream(run_id: str) -> StreamingResponse:
    """Stream research trace events for a given run via SSE."""
    logger.info(f"[API] GET /orchestration/{run_id}/research-stream — SSE client connected")

    async def event_generator():
        try:
            async for event in research_trace_service.subscribe_stream(run_id):
                event_type = event.get("event", "message")
                payload = json.dumps(event, default=str)
                yield f"event: {event_type}\ndata: {payload}\n\n"
        except Exception as e:
            logger.warning(f"[API] SSE stream error for run_id={run_id}: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

