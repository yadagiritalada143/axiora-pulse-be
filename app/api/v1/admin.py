"""Minimal, read-only administrator API routes."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_admin
from app.core.limiter import limiter
from app.db.database import get_db
from app.db.models import User
from app.models.admin_models import AdminUserListResponse, UserGrowthResponse
from app.services.admin_service import admin_service

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/users", response_model=AdminUserListResponse)
@limiter.limit("60/minute")
async def list_users(
    request: Request,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None, max_length=255),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserListResponse:
    """List user details for the administrator dashboard."""
    return await admin_service.list_users(db, limit, offset, search)


@router.get("/stats/user-growth", response_model=UserGrowthResponse)
@limiter.limit("60/minute")
async def user_growth(
    request: Request,
    granularity: Literal["month", "year"] = Query("month"),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserGrowthResponse:
    """Return new-user counts bucketed by month or year for the growth chart."""
    return await admin_service.get_user_growth(db, granularity)
