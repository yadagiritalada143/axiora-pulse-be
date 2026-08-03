"""
app/models/workspace_models.py
────────────────────────────────────────────────────────────────────────────────
Pydantic request/response models for all Workspace endpoints & sub-resources.

Endpoints covered:
  POST   /api/v1/workspaces                        → CreateWorkspaceRequest → WorkspaceResponse
  GET    /api/v1/workspaces                        → WorkspaceListResponse
  GET    /api/v1/workspaces/{id}                   → WorkspaceResponse
  DELETE /api/v1/workspaces/{id}                   → DeleteWorkspaceResponse (archives, is_delete=true)
  PATCH  /api/v1/workspaces/{id}/restore           → RestoreWorkspaceResponse (is_delete=false)
  POST   /api/v1/workspaces/{id}/chat              → WorkspaceChatRequest   → WorkspaceChatResponse
  GET    /api/v1/workspaces/{id}/state             → WorkspaceStateResponse
  POST   /api/v1/workspaces/{id}/reset             → WorkspaceStateResponse
  GET    /api/v1/workspaces/{id}/reports/{agent}   → Stream File Download (PDF/Doc)
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Request Models ─────────────────────────────────────────────────────────────

class CreateWorkspaceRequest(BaseModel):
    """Payload for POST /api/v1/workspaces."""
    name: str = Field(..., min_length=1, max_length=100, description="Workspace name")
    description: Optional[str] = Field(None, description="Optional workspace description")


class UpdateWorkspaceRequest(BaseModel):
    """Payload for PUT /api/v1/workspaces/{workspace_id}."""
    name: str = Field(..., min_length=1, max_length=100, description="Updated workspace name")
    description: Optional[str] = Field(None, description="Updated workspace description (can be null/empty)")


class WorkspaceChatRequest(BaseModel):
    """Payload for POST /api/v1/workspaces/{id}/chat."""
    message: str = Field(..., min_length=1, description="Message to send to AI Mentor inside this workspace")


class ExportWorkspaceReportRequest(BaseModel):
    """Payload for POST /api/v1/workspaces/{id}/reports/export."""
    agent_name: str = Field("idea_validation_agent", description="idea_validation_agent | market_research_agent | full")
    format: str = Field("pdf", description="Export format: pdf or doc")


# ── Response Models ────────────────────────────────────────────────────────────

class WorkspaceResponse(BaseModel):
    """Returned for a single workspace."""
    id: int
    user_id: int
    name: str
    description: Optional[str] = None
    state: str = "GATHERING_INFO"
    is_delete: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkspaceListResponse(BaseModel):
    """Returned for a list of workspaces."""
    total: int
    workspaces: List[WorkspaceResponse]


class WorkspaceStateResponse(BaseModel):
    """Returned for GET/POST /api/v1/workspaces/{id}/state or /reset."""
    id: int
    user_id: int
    name: str
    description: Optional[str] = None
    state: str = "GATHERING_INFO"
    idea: Dict[str, Any] = Field(default_factory=dict)
    conversation_history: List[Dict[str, Any]] = Field(default_factory=list)
    validation_result: Optional[Dict[str, Any]] = None
    is_delete: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkspaceChatResponse(BaseModel):
    """Returned after sending a message to AI Mentor in a workspace."""
    reply: str
    workspace_id: int
    state: str
    idea: Dict[str, Any]
    validation_result: Optional[Dict[str, Any]] = None


class DeleteWorkspaceResponse(BaseModel):
    """Returned after a workspace is archived (soft-deleted)."""
    status: str = "success"
    message: str = "Workspace archived successfully."
    workspace_id: int
    is_delete: bool = True


class RestoreWorkspaceResponse(BaseModel):
    """Returned after a workspace is restored from the archive."""
    status: str = "success"
    message: str = "Workspace restored successfully."
    workspace_id: int
    is_delete: bool = False
