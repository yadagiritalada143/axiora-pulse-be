"""
app/api/v1/analytics.py
────────────────────────────────────────────────────────────────────────────────
Token analytics API routes:
  - GET  /api/v1/analytics/tokens/me
  - GET  /api/v1/analytics/tokens/workspaces/{workspace_id}
  - GET  /api/v1/analytics/admin/tokens
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import User, Workspace
from app.models.token_models import (
    AdminTokenAnalyticsOut,
    TokenAnalyticsEnvelope,
    UserTokenSummaryOut,
    WorkspaceTokenSummaryOut,
)
from app.services.token_tracking_service import token_tracking_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get(
    "/tokens/me",
    response_model=TokenAnalyticsEnvelope,
    status_code=status.HTTP_200_OK,
    summary="Get token usage analytics for the current user",
    description="Returns aggregated token consumption, cost, per-workspace breakdown, and daily usage for the authenticated user.",
)
async def get_my_token_analytics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TokenAnalyticsEnvelope:
    logger.info("[Analytics] Fetching token analytics for user_id=%s (%s)", current_user.id, current_user.username)
    summary: UserTokenSummaryOut = await token_tracking_service.get_user_summary(
        user_id=current_user.id,
        db=db,
    )
    return TokenAnalyticsEnvelope(
        success=True,
        data=summary,
        message="User token usage analytics retrieved successfully",
    )


@router.get(
    "/tokens/totals/me",
    response_model=TokenAnalyticsEnvelope,
    status_code=status.HTTP_200_OK,
    summary="Get the single cumulative token total record for the current user",
    description="Returns the 1-row cumulative totals (prompt_tokens, completion_tokens, total_tokens, total_cost, total_calls) for the user.",
)
async def get_my_token_totals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TokenAnalyticsEnvelope:
    logger.info("[Analytics] Fetching 1-row token totals for user_id=%s", current_user.id)
    totals = await token_tracking_service.get_user_total(
        user_id=current_user.id,
        db=db,
    )
    return TokenAnalyticsEnvelope(
        success=True,
        data=totals,
        message="User cumulative token totals retrieved successfully",
    )


@router.get(
    "/tokens/workspaces/{workspace_id}",
    response_model=TokenAnalyticsEnvelope,
    status_code=status.HTTP_200_OK,
    summary="Get token usage analytics for a specific workspace",
    description="Returns token consumption breakdown (mentor chat, idea extraction, orchestration runs) and recent logs for a workspace.",
)
async def get_workspace_token_analytics(
    workspace_id: int,
    limit_logs: int = Query(50, ge=1, le=200, description="Max recent log entries to return"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TokenAnalyticsEnvelope:
    # Verify workspace ownership / access
    workspace = await db.get(Workspace, workspace_id)
    if not workspace or workspace.is_delete:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace #{workspace_id} not found.",
        )
    if workspace.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view analytics for this workspace.",
        )

    logger.info("[Analytics] Fetching token analytics for workspace_id=%s user_id=%s", workspace_id, current_user.id)
    summary: WorkspaceTokenSummaryOut = await token_tracking_service.get_workspace_summary(
        workspace_id=workspace_id,
        user_id=workspace.user_id,
        db=db,
        limit_logs=limit_logs,
    )
    return TokenAnalyticsEnvelope(
        success=True,
        data=summary,
        message=f"Workspace #{workspace_id} token usage analytics retrieved successfully",
    )


@router.get(
    "/admin/tokens",
    response_model=TokenAnalyticsEnvelope,
    status_code=status.HTTP_200_OK,
    summary="Get platform-wide token analytics (Admin only)",
    description="Returns global platform token burn, top token consumers, model distribution, and source breakdown.",
)
async def get_admin_token_analytics(
    top_n: int = Query(20, ge=1, le=100, description="Number of top users to retrieve"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TokenAnalyticsEnvelope:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required.",
        )

    logger.info("[Analytics] Admin token analytics requested by user_id=%s", current_user.id)
    analytics: AdminTokenAnalyticsOut = await token_tracking_service.get_admin_analytics(
        db=db,
        top_n=top_n,
    )
    return TokenAnalyticsEnvelope(
        success=True,
        data=analytics,
        message="Platform token analytics retrieved successfully",
    )
