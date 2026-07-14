"""
Orchestration API Routes  —  /api/v1/orchestration
──────────────────────────────────────────────────────────────────────────────
POST /api/v1/orchestration/run  →  Start a full orchestration run

Health checks are handled globally at GET /health (see main.py).
"""
import logging

from fastapi import APIRouter, HTTPException, status

from app.models.orchestration_models import OrchestrationRequest, OrchestrationResponse
from app.orchestration.orchestrator import orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orchestration", tags=["Orchestration"])


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

