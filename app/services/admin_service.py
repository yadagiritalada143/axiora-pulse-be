"""Read-only administrator operations."""

import logging
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Survey, User, Workspace
from app.models.admin_models import (
    AdminSurveyListResponse,
    AdminSurveyPagination,
    AdminSurveyResponse,
    AdminUserListResponse,
    AdminUserPagination,
    AdminUserResponse,
    UserGrowthPoint,
    UserGrowthResponse,
)

logger = logging.getLogger(__name__)


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
        logger.info(
            "Admin user list fetched: %s of %s users (limit=%s, offset=%s, search=%s)",
            len(rows), total, limit, offset, bool(search),
        )
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

    async def list_surveys(
        self,
        db: AsyncSession,
        limit: int,
        offset: int,
        search: str | None,
        user_id: int | None = None,
    ) -> AdminSurveyListResponse:
        """Return a paginated directory of surveys, with owner username.

        Covers all users by default; pass ``user_id`` to scope to one user's surveys.
        """
        filters = []
        if search:
            term = f"%{search.strip()}%"
            filters.append(User.username.ilike(term))
        if user_id is not None:
            filters.append(Survey.user_id == user_id)

        total_statement = select(func.count(Survey.id)).join(User, User.id == Survey.user_id)
        surveys_statement = (
            select(Survey, User.username, Workspace.name)
            .join(User, User.id == Survey.user_id)
            .join(Workspace, Workspace.id == Survey.workspace_id)
            .order_by(Survey.created_at.desc(), Survey.id.desc())
            .offset(offset)
            .limit(limit)
        )
        if filters:
            total_statement = total_statement.where(*filters)
            surveys_statement = surveys_statement.where(*filters)

        total = (await db.execute(total_statement)).scalar_one()
        rows = (await db.execute(surveys_statement)).all()
        logger.info(
            "Admin survey list fetched: %s of %s surveys (limit=%s, offset=%s, search=%s)",
            len(rows), total, limit, offset, bool(search),
        )
        surveys = [
            AdminSurveyResponse(
                id=survey.id,
                user_id=survey.user_id,
                owner_username=username,
                workspace_id=survey.workspace_id,
                workspace_name=workspace_name,
                survey_link=survey.survey_link,
                question_count=len(survey.questions or []),
                created_at=survey.created_at,
                updated_at=survey.updated_at,
            )
            for survey, username, workspace_name in rows
        ]
        return AdminSurveyListResponse(
            surveys=surveys,
            pagination=AdminSurveyPagination(total=total, limit=limit, offset=offset),
        )

    async def get_user_growth(
        self,
        db: AsyncSession,
        granularity: str,
    ) -> UserGrowthResponse:
        """Return new-user counts bucketed by ``granularity`` ("month" or "year").

        The period label is produced in SQL (dialect-aware, so the same code runs
        on Postgres in production and SQLite under test), then the sparse series is
        zero-filled in Python so the chart's axis is continuous from the first
        signup through the current period.
        """
        period = self._period_expression(db, granularity)
        statement = (
            select(period.label("period"), func.count(User.id).label("count"))
            .group_by(period)
            .order_by(period)
        )
        rows = (await db.execute(statement)).all()
        counts = {row.period: row.count for row in rows}
        logger.info(
            "Admin user growth fetched: %s populated %s-bucket(s)",
            len(counts), granularity,
        )

        series = [
            UserGrowthPoint(period=label, count=counts.get(label, 0))
            for label in self._period_range(granularity, earliest=min(counts) if counts else None)
        ]
        return UserGrowthResponse(granularity=granularity, series=series)

    @staticmethod
    def _period_expression(db: AsyncSession, granularity: str):
        """Build a SQL expression that formats ``created_at`` into a period label."""
        dialect = db.bind.dialect.name
        if dialect == "sqlite":
            fmt = "%Y-%m" if granularity == "month" else "%Y"
            return func.strftime(fmt, User.created_at)
        # Postgres (and any other backend that supports to_char).
        fmt = "YYYY-MM" if granularity == "month" else "YYYY"
        return func.to_char(User.created_at, fmt)

    @staticmethod
    def _period_range(granularity: str, earliest: str | None) -> list[str]:
        """Yield every period label from ``earliest`` through the current period.

        Returns an empty list when there are no users yet.
        """
        if earliest is None:
            return []
        now = datetime.now(timezone.utc)
        if granularity == "year":
            start_year = int(earliest)
            return [str(year) for year in range(start_year, now.year + 1)]

        start_year, start_month = (int(part) for part in earliest.split("-"))
        labels: list[str] = []
        year, month = start_year, start_month
        while (year, month) <= (now.year, now.month):
            labels.append(f"{year:04d}-{month:02d}")
            month += 1
            if month > 12:
                month = 1
                year += 1
        return labels


admin_service = AdminService()
