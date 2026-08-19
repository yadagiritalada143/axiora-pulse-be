"""Request and response schemas for the minimal administrator API."""

from datetime import datetime

from pydantic import BaseModel


class AdminUserResponse(BaseModel):
    """Safe user details displayed in the administrator directory."""

    id: int
    username: str
    display_name: str | None = None
    role: str
    created_at: datetime
    workspace_count: int


class AdminUserPagination(BaseModel):
    total: int
    limit: int
    offset: int


class AdminUserListResponse(BaseModel):
    users: list[AdminUserResponse]
    pagination: AdminUserPagination


class UserGrowthPoint(BaseModel):
    """Number of users that registered within a single period."""

    period: str  # "YYYY-MM" for month granularity, "YYYY" for year granularity
    count: int


class UserGrowthResponse(BaseModel):
    """New-user counts bucketed by period for the growth chart."""

    granularity: str  # "month" | "year"
    series: list[UserGrowthPoint]
