"""Minimal, read-only administrator API routes."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_admin
from app.core.limiter import limiter
from app.db.database import get_db
from app.db.models import User
from app.models.admin_models import (
    AdminDashboardStatsResponse,
    AdminSurveyListResponse,
    AdminSurveyResponseDetailResponse,
    AdminSurveyResponsesListResponse,
    AdminUserListResponse,
    AdminUserSurveySummaryResponse,
    RevenueResponse,
    UserGrowthAnalyticsResponse,
    UserGrowthResponse,
    UsersByPlanResponse,
)
from app.models.user_details_models import SetProfileStatusRequest, UserDetailsResponse
from app.services.admin_service import admin_service
from app.services.user_details_service import user_details_service

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


@router.get("/users/surveys", response_model=AdminSurveyListResponse)
@limiter.limit("60/minute")
async def list_surveys(
    request: Request,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None, max_length=255),
    user_id: int | None = Query(None, ge=1, description="Restrict results to surveys owned by this user"),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminSurveyListResponse:
    """List surveys created by all users, for the administrator dashboard.

    Pass `user_id` to view a single user's surveys instead of everyone's.
    """
    return await admin_service.list_surveys(db, limit, offset, search, user_id)


@router.get("/surveys/{survey_id}/responses", response_model=AdminSurveyResponsesListResponse)
@limiter.limit("60/minute")
async def list_survey_responses(
    request: Request,
    survey_id: int,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None, max_length=255),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminSurveyResponsesListResponse:
    """List collected responses for any survey, for the administrator dashboard."""
    return await admin_service.list_survey_responses(db, survey_id, limit, offset, search)


@router.get(
    "/surveys/{survey_id}/responses/{response_id}",
    response_model=AdminSurveyResponseDetailResponse,
)
@limiter.limit("60/minute")
async def get_survey_response_detail(
    request: Request,
    survey_id: int,
    response_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminSurveyResponseDetailResponse:
    """Get one collected survey response, including enriched answer preview."""
    return await admin_service.get_survey_response_detail(db, survey_id, response_id)


@router.get("/users/{user_id}/survey-summary", response_model=AdminUserSurveySummaryResponse)
@limiter.limit("60/minute")
async def get_user_survey_summary(
    request: Request,
    user_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserSurveySummaryResponse:
    """
    Get a summary of a user's surveys and responses, for the administrator dashboard.
    """
    return await admin_service.get_user_survey_summary(db, user_id)


@router.patch("/user-details/{user_id}/status", response_model=UserDetailsResponse)
@limiter.limit("30/minute")
async def set_user_details_status(
    request: Request,
    user_id: int,
    payload: SetProfileStatusRequest,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserDetailsResponse:
    """Set a user's profile_status (Active/Inactive/Suspended) in user_details, by user_id."""
    return await user_details_service.set_status_by_user_id(user_id, payload.profile_status, db)


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


@router.get("/dashboard/stats", response_model=AdminDashboardStatsResponse)
@limiter.limit("60/minute")
async def dashboard_stats(
    request: Request,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminDashboardStatsResponse:
    """Return headline user/workspace counts and week-over-week growth."""
    return await admin_service.get_dashboard_stats(db)


@router.get("/analytics/user-growth", response_model=UserGrowthAnalyticsResponse)
@limiter.limit("60/minute")
async def analytics_user_growth(
    request: Request,
    period: Literal["week", "month", "last_7_days", "last_30_days", "year"] = Query("month"),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserGrowthAnalyticsResponse:
    """Return user registrations bucketed by date for the requested period."""
    return await admin_service.get_user_growth_analytics(db, period)


@router.get("/analytics/users-by-plan", response_model=UsersByPlanResponse)
@limiter.limit("60/minute")
async def analytics_users_by_plan(
    request: Request,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UsersByPlanResponse:
    """Return the distribution of users across subscription plans."""
    return await admin_service.get_users_by_plan(db)


@router.get("/analytics/revenue", response_model=RevenueResponse)
@limiter.limit("60/minute")
async def analytics_revenue(
    request: Request,
    period: Literal["today", "week", "month", "year"] = Query("month"),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> RevenueResponse:
    """Return successful payment revenue aggregated over the requested period."""
    return await admin_service.get_revenue(db, period)
