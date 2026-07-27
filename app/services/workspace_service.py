"""
app/services/workspace_service.py
────────────────────────────────────────────────────────────────────────────────
Workspace service — all database operations & sub-resource handlers for workspaces.

Operations:
  create_workspace()             → Persist a new workspace scoped to the current user.
  list_workspaces()              → Fetch all workspaces belonging to the current user.
  get_workspace()                → Fetch a single workspace by ID (owner-enforced).
  get_workspaces_by_user_id()    → Fetch all workspaces for a given user_id (self-service enforced).
  delete_workspace()             → Hard-delete a workspace by ID (owner-enforced).
  process_mentor_chat()          → Process AI Mentor message in a workspace (owner-enforced).
  get_workspace_state()          → Fetch full workspace dialogue & validation state (owner-enforced).
  reset_workspace_mentor()       → Reset mentor dialogue for a workspace (owner-enforced).
  export_workspace_report()      → Export PDF/Doc report for a workspace (owner-enforced).
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from fastapi import HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, Workspace
from app.models.workspace_models import (
    CreateWorkspaceRequest,
    UpdateWorkspaceRequest,
    WorkspaceChatRequest,
    WorkspaceChatResponse,
    WorkspaceListResponse,
    WorkspaceResponse,
    WorkspaceStateResponse,
)
from app.services.mentor_service import mentor_service, WorkspaceMentorState
from app.services.report_service import report_service

logger = logging.getLogger(__name__)


class WorkspaceService:
    """Stateless service — all state lives in the DB session."""

    # ── Create ────────────────────────────────────────────────────────────────

    async def create_workspace(
        self,
        payload: CreateWorkspaceRequest,
        current_user: User,
        db: AsyncSession,
    ) -> WorkspaceResponse:
        """Create a new workspace owned by current_user."""
        now = datetime.now(timezone.utc)

        workspace = Workspace(
            user_id=current_user.id,
            name=payload.name.strip(),
            description=payload.description.strip() if payload.description else None,
            state="GATHERING_INFO",
            idea={
                "idea_title": None,
                "idea_description": None,
                "problem_statement": None,
                "industry": "general",
                "founder_validation_goal": "validate my idea",
                "geography": "global"
            },
            conversation_history=[],
            validation_result=None,
            created_at=now,
            updated_at=now,
        )

        db.add(workspace)
        await db.flush()   # Populate `workspace.id` without committing yet.
        await db.refresh(workspace)

        logger.info(
            "Workspace created: id=%s name=%r user_id=%s",
            workspace.id, workspace.name, current_user.id,
        )
        return WorkspaceResponse.model_validate(workspace)

    # ── List ──────────────────────────────────────────────────────────────────

    async def list_workspaces(
        self,
        current_user: User,
        db: AsyncSession,
    ) -> WorkspaceListResponse:
        """Return all workspaces owned by current_user."""
        result = await db.execute(
            select(Workspace)
            .where(Workspace.user_id == current_user.id)
            .order_by(Workspace.created_at.desc())
        )
        workspaces = result.scalars().all()

        return WorkspaceListResponse(
            total=len(workspaces),
            workspaces=[WorkspaceResponse.model_validate(w) for w in workspaces],
        )

    # ── Get by ID ─────────────────────────────────────────────────────────────

    async def get_workspace(
        self,
        workspace_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> WorkspaceResponse:
        """Return a single workspace — 404 if not found, 403 if not owner."""
        workspace = await self._fetch_owned_workspace(workspace_id, current_user, db)
        return WorkspaceResponse.model_validate(workspace)

    # ── Update ────────────────────────────────────────────────────────────────

    async def update_workspace(
        self,
        workspace_id: int,
        payload: UpdateWorkspaceRequest,
        current_user: User,
        db: AsyncSession,
    ) -> WorkspaceResponse:
        """Update name and/or description of an owned workspace — 404/403 enforced."""
        workspace = await self._fetch_owned_workspace(workspace_id, current_user, db)

        workspace.name = payload.name.strip()
        workspace.description = payload.description.strip() if payload.description else None
        workspace.updated_at = datetime.now(timezone.utc)

        await db.flush()
        await db.refresh(workspace)

        logger.info(
            "Workspace updated: id=%s user_id=%s",
            workspace.id, current_user.id,
        )
        return WorkspaceResponse.model_validate(workspace)

    # ── Get by User ID ────────────────────────────────────────────────────────

    async def get_workspaces_by_user_id(
        self,
        user_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> WorkspaceListResponse:
        """Return all workspaces for a given user_id."""
        if user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view workspaces for this user.",
            )

        result = await db.execute(
            select(Workspace)
            .where(Workspace.user_id == user_id)
            .order_by(Workspace.created_at.desc())
        )
        workspaces = result.scalars().all()

        return WorkspaceListResponse(
            total=len(workspaces),
            workspaces=[WorkspaceResponse.model_validate(w) for w in workspaces],
        )

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete_workspace(
        self,
        workspace_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> None:
        """Hard-delete a workspace — 404 if not found, 403 if not owner."""
        workspace = await self._fetch_owned_workspace(workspace_id, current_user, db)

        await db.delete(workspace)
        logger.info(
            "Workspace deleted: id=%s user_id=%s",
            workspace_id, current_user.id,
        )

    # ── Mentor Chat Sub-resource ──────────────────────────────────────────────

    async def process_mentor_chat(
        self,
        workspace_id: int,
        payload: WorkspaceChatRequest,
        current_user: User,
        db: AsyncSession,
    ) -> WorkspaceChatResponse:
        """Process AI Mentor message inside a workspace."""
        workspace = await self._fetch_owned_workspace(workspace_id, current_user, db)

        ws_state = WorkspaceMentorState(
            workspace_id=str(workspace.id),
            state=workspace.state or "GATHERING_INFO",
            idea=workspace.idea or {},
            conversation_history=workspace.conversation_history or [],
            validation_result=workspace.validation_result
        )

        updated_state = await mentor_service.process_message(ws_state, payload.message)

        # Save back to database
        workspace.state = updated_state.state
        workspace.idea = updated_state.idea
        workspace.conversation_history = list(updated_state.conversation_history)
        workspace.validation_result = updated_state.validation_result
        workspace.updated_at = datetime.now(timezone.utc)

        await db.flush()
        await db.refresh(workspace)

        assistant_reply = "I'm listening. Tell me more!"
        if updated_state.conversation_history:
            for msg in reversed(updated_state.conversation_history):
                if msg.get("role") == "assistant":
                    assistant_reply = msg.get("content", "")
                    break

        return WorkspaceChatResponse(
            reply=assistant_reply,
            workspace_id=workspace.id,
            state=workspace.state,
            idea=workspace.idea,
            validation_result=workspace.validation_result
        )

    # ── Workspace State Sub-resource ──────────────────────────────────────────

    async def get_workspace_state(
        self,
        workspace_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> WorkspaceStateResponse:
        """Fetch complete workspace dialogue, idea context & validation result."""
        workspace = await self._fetch_owned_workspace(workspace_id, current_user, db)
        return WorkspaceStateResponse.model_validate(workspace)

    # ── Reset Mentor Sub-resource ─────────────────────────────────────────────

    async def reset_workspace_mentor(
        self,
        workspace_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> WorkspaceStateResponse:
        """Reset conversation dialogue state for a workspace."""
        workspace = await self._fetch_owned_workspace(workspace_id, current_user, db)

        default_idea = {
            "idea_title": None,
            "idea_description": None,
            "problem_statement": None,
            "industry": "general",
            "founder_validation_goal": "validate my idea",
            "geography": "global"
        }

        initial_greeting = (
            "Hello! I'm your AI Mentor at Axiora Pulse. "
            "Tell me about your startup idea and the problem you're solving — "
            "and together we'll validate its potential!"
        )

        workspace.state = "GATHERING_INFO"
        workspace.idea = default_idea
        workspace.conversation_history = [{"role": "assistant", "content": initial_greeting}]
        workspace.validation_result = None
        workspace.updated_at = datetime.now(timezone.utc)

        await db.flush()
        await db.refresh(workspace)

        return WorkspaceStateResponse.model_validate(workspace)

    # ── Report Export Sub-resource ────────────────────────────────────────────

    async def export_workspace_report(
        self,
        workspace_id: int,
        agent_name: str,
        export_format: str,
        current_user: User,
        db: AsyncSession,
    ) -> Response:
        """Generate and download PDF or Doc report for a workspace."""
        workspace = await self._fetch_owned_workspace(workspace_id, current_user, db)

        if not workspace.validation_result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Workspace {workspace_id} has not been validated yet. Please run validation first."
            )

        idea_info = workspace.idea or {"idea_title": workspace.name}

        file_bytes, media_type, filename = report_service.generate_report(
            agent_name=agent_name,
            validation_result=workspace.validation_result,
            idea_info=idea_info,
            export_format=export_format
        )

        return Response(
            content=file_bytes,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _fetch_owned_workspace(
        self,
        workspace_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> Workspace:
        """Fetch a workspace and enforce ownership."""
        result = await db.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        )
        workspace = result.scalar_one_or_none()

        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workspace {workspace_id} not found.",
            )

        if workspace.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this workspace.",
            )

        return workspace


# ── Singleton ─────────────────────────────────────────────────────────────────
workspace_service = WorkspaceService()
