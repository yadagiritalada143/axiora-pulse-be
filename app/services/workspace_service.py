"""
app/services/workspace_service.py
────────────────────────────────────────────────────────────────────────────────
Workspace service — all database operations for workspaces.

Operations:
  create_workspace()             → Persist a new workspace scoped to the current user.
  list_workspaces()              → Fetch all workspaces belonging to the current user.
  get_workspace()                → Fetch a single workspace by ID (owner-enforced).
  get_workspaces_by_user_id()    → Fetch all workspaces for a given user_id (self-service enforced).
  delete_workspace()             → Hard-delete a workspace by ID (owner-enforced).
"""
import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, Workspace
from app.models.workspace_models import (
    CreateWorkspaceRequest,
    DeleteWorkspaceResponse,
    WorkspaceListResponse,
    WorkspaceResponse,
)

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

    # ── Get by User ID ────────────────────────────────────────────────────────

    async def get_workspaces_by_user_id(
        self,
        user_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> WorkspaceListResponse:
        """Return all workspaces for a given user_id.

        Self-service only — users can only query their own user_id.

        Raises:
            HTTP 403 — requested user_id does not match the authenticated user.
        """
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

        logger.info(
            "Fetched %d workspace(s) for user_id=%s",
            len(workspaces), user_id,
        )

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
    ) -> DeleteWorkspaceResponse:
        """Hard-delete a workspace — 404 if not found, 403 if not owner."""
        workspace = await self._fetch_owned_workspace(workspace_id, current_user, db)

        await db.delete(workspace)
        logger.info(
            "Workspace deleted: id=%s user_id=%s",
            workspace_id, current_user.id,
        )

        return DeleteWorkspaceResponse(
            status="success",
            message="Workspace deleted successfully.",
            workspace_id=workspace_id,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _fetch_owned_workspace(
        self,
        workspace_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> Workspace:
        """Fetch a workspace and enforce ownership.

        Raises:
            HTTP 404 — workspace does not exist.
            HTTP 403 — workspace exists but belongs to another user.
        """
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
