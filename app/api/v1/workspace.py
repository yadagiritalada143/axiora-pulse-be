"""
app/api/v1/workspace.py
────────────────────────────────────────────────────────────────────────────────
Workspace router — create, list, get, and delete workspaces.

All endpoints require a valid JWT Bearer token (get_current_user dependency).

Routes:
  POST   /api/v1/workspaces                  → create_workspace
  GET    /api/v1/workspaces                  → list_workspaces
  GET    /api/v1/workspaces/user/{user_id}   → get_workspaces_by_user_id
  GET    /api/v1/workspaces/{id}             → get_workspace
  DELETE /api/v1/workspaces/{id}             → delete_workspace
"""
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import limiter
from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import User
from app.models.workspace_models import (
    CreateWorkspaceRequest,
    DeleteWorkspaceResponse,
    WorkspaceListResponse,
    WorkspaceResponse,
)
from app.services.workspace_service import workspace_service

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


# ── Create Workspace ──────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new workspace",
    description=(
        "Creates a new workspace scoped to the authenticated user. "
        "Requires a valid JWT Bearer token. "
        "Returns the newly created workspace object."
    ),
)
@limiter.limit("20/minute")
async def create_workspace(
    request: Request,
    payload: CreateWorkspaceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    return await workspace_service.create_workspace(payload, current_user, db)


# ── List Workspaces ───────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=WorkspaceListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all workspaces for the current user",
    description=(
        "Returns all workspaces owned by the authenticated user, "
        "ordered by creation date (newest first). "
        "Requires a valid JWT Bearer token."
    ),
)
@limiter.limit("60/minute")
async def list_workspaces(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceListResponse:
    return await workspace_service.list_workspaces(current_user, db)


# ── Get Workspaces by User ID ─────────────────────────────────────────

@router.get(
    "/user/{user_id}",
    response_model=WorkspaceListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get all workspaces for a specific user ID",
    description=(
        "Returns all workspaces belonging to the given user_id. "
        "Self-service only — the authenticated user can only query their own user_id. "
        "Returns 403 if the user_id does not match the authenticated user. "
        "Requires a valid JWT Bearer token."
    ),
)
@limiter.limit("60/minute")
async def get_workspaces_by_user_id(
    request: Request,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceListResponse:
    return await workspace_service.get_workspaces_by_user_id(user_id, current_user, db)


# ── Get Workspace by ID ───────────────────────────────────────────────────────

@router.get(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a workspace by ID",
    description=(
        "Fetches a single workspace by its numeric ID. "
        "Returns 404 if not found, 403 if the workspace belongs to another user. "
        "Requires a valid JWT Bearer token."
    ),
)
@limiter.limit("60/minute")
async def get_workspace(
    request: Request,
    workspace_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    return await workspace_service.get_workspace(workspace_id, current_user, db)


# ── Delete Workspace ──────────────────────────────────────────────────────────

@router.delete(
    "/{workspace_id}",
    response_model=DeleteWorkspaceResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete a workspace by ID",
    description=(
        "Permanently deletes a workspace and all associated data. "
        "Returns 404 if not found, 403 if the workspace belongs to another user. "
        "Requires a valid JWT Bearer token."
    ),
)
@limiter.limit("20/minute")
async def delete_workspace(
    request: Request,
    workspace_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeleteWorkspaceResponse:
    return await workspace_service.delete_workspace(workspace_id, current_user, db)
