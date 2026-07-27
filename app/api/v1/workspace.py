"""
app/api/v1/workspace.py
────────────────────────────────────────────────────────────────────────────────
Workspace router — CRUD and workspace-owned sub-resources:
  - Create, List, Retrieve, Delete workspaces
  - Send message to AI Mentor in workspace
  - Get full workspace dialogue state & validation results
  - Reset workspace conversation state
  - Export PDF/Doc reports per agent for workspace

All endpoints require a valid JWT Bearer token (get_current_user dependency).

Routes:
  POST   /api/v1/workspaces                        → create_workspace
  GET    /api/v1/workspaces                        → list_workspaces
  GET    /api/v1/workspaces/user/{user_id}         → get_workspaces_by_user_id
  GET    /api/v1/workspaces/{id}                   → get_workspace
  PUT    /api/v1/workspaces/{id}                   → update_workspace
  DELETE /api/v1/workspaces/{id}                   → delete_workspace
  POST   /api/v1/workspaces/{id}/chat              → chat_workspace_mentor
  GET    /api/v1/workspaces/{id}/state             → get_workspace_state
  POST   /api/v1/workspaces/{id}/reset             → reset_workspace_mentor
  GET    /api/v1/workspaces/{id}/reports/{agent}   → download_workspace_agent_report
  POST   /api/v1/workspaces/{id}/reports/export    → export_workspace_report
"""
from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.limiter import limiter
from app.db.database import get_db
from app.db.models import User
from app.models.workspace_models import (
    CreateWorkspaceRequest,
    ExportWorkspaceReportRequest,
    UpdateWorkspaceRequest,
    WorkspaceChatRequest,
    WorkspaceChatResponse,
    WorkspaceListResponse,
    WorkspaceResponse,
    WorkspaceStateResponse,
)
from app.services.workspace_service import workspace_service

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


# ── Create Workspace ──────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new workspace",
    description="Creates a new workspace scoped to the authenticated user.",
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
    description="Returns all workspaces owned by the authenticated user.",
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
    description="Returns all workspaces belonging to the given user_id.",
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
    description="Fetches a single workspace by its ID.",
)
@limiter.limit("60/minute")
async def get_workspace(
    request: Request,
    workspace_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    return await workspace_service.get_workspace(workspace_id, current_user, db)


# ── Update Workspace ────────────────────────────────────────────────────────

@router.put(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a workspace by ID",
    description="Updates the name and/or description of a workspace owned by the authenticated user.",
)
@limiter.limit("20/minute")
async def update_workspace(
    request: Request,
    workspace_id: int,
    payload: UpdateWorkspaceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    return await workspace_service.update_workspace(workspace_id, payload, current_user, db)


# ── Delete Workspace ──────────────────────────────────────────────────────────

@router.delete(
    "/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a workspace by ID",
    description="Permanently deletes a workspace and all associated data.",
)
@limiter.limit("20/minute")
async def delete_workspace(
    request: Request,
    workspace_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await workspace_service.delete_workspace(workspace_id, current_user, db)


# ── Workspace AI Mentor Chat Sub-resource ───────────────────────────────────────

@router.post(
    "/{workspace_id}/chat",
    response_model=WorkspaceChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a message to AI Mentor inside a workspace",
    description="Sends a message to the AI Mentor for the given workspace, updates idea context, and runs validation when ready.",
)
@limiter.limit("30/minute")
async def chat_workspace_mentor(
    request: Request,
    workspace_id: int,
    payload: WorkspaceChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceChatResponse:
    return await workspace_service.process_mentor_chat(workspace_id, payload, current_user, db)


# ── Workspace Full State Sub-resource ───────────────────────────────────────────

@router.get(
    "/{workspace_id}/state",
    response_model=WorkspaceStateResponse,
    status_code=status.HTTP_200_OK,
    summary="Get workspace dialogue history & validation state",
    description="Retrieves full conversation history, extracted idea details, and agent validation results for a workspace.",
)
@limiter.limit("60/minute")
async def get_workspace_state(
    request: Request,
    workspace_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceStateResponse:
    return await workspace_service.get_workspace_state(workspace_id, current_user, db)


# ── Workspace Reset Sub-resource ───────────────────────────────────────────────

@router.post(
    "/{workspace_id}/reset",
    response_model=WorkspaceStateResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset workspace mentor conversation",
    description="Resets the conversation dialogue state and extracted idea context for a workspace.",
)
@limiter.limit("20/minute")
async def reset_workspace_mentor(
    request: Request,
    workspace_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceStateResponse:
    return await workspace_service.reset_workspace_mentor(workspace_id, current_user, db)


# ── Workspace Agent Report Download Sub-resource ───────────────────────────────

@router.get(
    "/{workspace_id}/reports/{agent_name}",
    summary="Download agent report for a workspace",
    description="Generates and downloads a report for a specific agent (idea_validation_agent, market_research_agent, or full) from a workspace.",
)
@limiter.limit("30/minute")
async def download_workspace_agent_report(
    request: Request,
    workspace_id: int,
    agent_name: str,
    format: str = Query("pdf", description="Export format: pdf or doc"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await workspace_service.export_workspace_report(workspace_id, agent_name, format, current_user, db)


@router.post(
    "/{workspace_id}/reports/export",
    summary="Export agent report for a workspace via POST",
    description="Generates and downloads an agent report (PDF or Doc) for the workspace.",
)
@limiter.limit("30/minute")
async def export_workspace_report(
    request: Request,
    workspace_id: int,
    payload: ExportWorkspaceReportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await workspace_service.export_workspace_report(
        workspace_id=workspace_id,
        agent_name=payload.agent_name,
        export_format=payload.format,
        current_user=current_user,
        db=db
    )
