"""Read-only administrator operations."""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, Workspace
from app.models.admin_models import (
    AdminUserListResponse,
    AdminUserPagination,
    AdminUserResponse,
)


class AdminService:
    async def list_users(
        self,
        db: AsyncSession,
        limit: int,
        offset: int,
        search: str | None,
    ) -> AdminUserListResponse:
        """Return a paginated user directory with each user's workspace count."""
        filters = []
        if search:
            term = f"%{search.strip()}%"
            filters.append(or_(User.username.ilike(term), User.display_name.ilike(term)))

        total_statement = select(func.count(User.id))
        users_statement = (
            select(User, func.count(Workspace.id).label("workspace_count"))
            .outerjoin(Workspace, Workspace.user_id == User.id)
            .group_by(User.id)
            .order_by(User.created_at.desc(), User.id.desc())
            .offset(offset)
            .limit(limit)
        )
        if filters:
            total_statement = total_statement.where(*filters)
            users_statement = users_statement.where(*filters)

        total = (await db.execute(total_statement)).scalar_one()
        rows = (await db.execute(users_statement)).all()
        users = [
            AdminUserResponse(
                id=user.id,
                username=user.username,
                display_name=user.display_name,
                role=user.role,
                created_at=user.created_at,
                workspace_count=workspace_count,
            )
            for user, workspace_count in rows
        ]
        return AdminUserListResponse(
            users=users,
            pagination=AdminUserPagination(total=total, limit=limit, offset=offset),
        )


admin_service = AdminService()
