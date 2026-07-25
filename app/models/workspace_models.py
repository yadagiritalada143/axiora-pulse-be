"""
app/models/workspace_models.py
────────────────────────────────────────────────────────────────────────────────
Pydantic request/response models for all workspace endpoints.

Endpoints covered:
  POST   /api/v1/workspaces          → CreateWorkspaceRequest  → WorkspaceResponse
  GET    /api/v1/workspaces          → (no body)               → WorkspaceListResponse
  GET    /api/v1/workspaces/{id}     → (no body)               → WorkspaceResponse
  DELETE /api/v1/workspaces/{id}     → (no body)               → DeleteWorkspaceResponse
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ── Request Models ─────────────────────────────────────────────────────────────

class CreateWorkspaceRequest(BaseModel):
    """Payload for POST /api/v1/workspaces."""
    name: str = Field(..., min_length=1, max_length=255, description="Workspace name")
    description: Optional[str] = Field(None, description="Optional workspace description")


# ── Response Models ────────────────────────────────────────────────────────────

class WorkspaceResponse(BaseModel):
    """Returned for a single workspace."""
    id: int
    user_id: int
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkspaceListResponse(BaseModel):
    """Returned for a list of workspaces."""
    total: int
    workspaces: List[WorkspaceResponse]


class DeleteWorkspaceResponse(BaseModel):
    """Returned after a successful workspace deletion."""
    status: str = "success"
    message: str = "Workspace deleted successfully."
    workspace_id: int
