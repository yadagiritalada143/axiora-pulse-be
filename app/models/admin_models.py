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
