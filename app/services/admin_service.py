"""Read-only administrator operations."""

import logging
import os
from datetime import datetime, timezone

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import HTTPException, status

from app.db.models import PublicSurveyResponse, Survey, User, UserDetails, Workspace
from app.models.admin_models import (
    AdminSurveyAnswerPreviewItem,
    AdminSurveyListResponse,
    AdminSurveyPagination,
    AdminSurveyResponse,
    AdminSurveyResponseDetailResponse,
    AdminSurveyResponseItem,
    AdminSurveyResponsePagination,
    AdminSurveyResponsesListResponse,
    AdminUserListResponse,
    AdminUserPagination,
    AdminUserResponse,
    AdminUserSurveySummaryResponse,
    AdminUserSurveySummaryItem,
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

        responses_subq = (
            select(
                PublicSurveyResponse.survey_id.label("survey_id"),
                func.count(PublicSurveyResponse.id).label("responses_count"),
            )
            .group_by(PublicSurveyResponse.survey_id)
            .subquery()
        )

        total_statement = select(func.count(Survey.id)).join(User, User.id == Survey.user_id)
        surveys_statement = (
            select(
                Survey,
                User.username,
                Workspace.name,
                Workspace.description,
                func.coalesce(responses_subq.c.responses_count, 0),
            )
            .join(User, User.id == Survey.user_id)
            .join(Workspace, Workspace.id == Survey.workspace_id)
            .outerjoin(responses_subq, responses_subq.c.survey_id == Survey.id)
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
            self._build_admin_survey_response(
                survey=survey,
                owner_username=username,
                workspace_name=workspace_name,
                workspace_description=workspace_description,
                responses_count=responses_count,
            )
            for survey, username, workspace_name, workspace_description, responses_count in rows
        ]
        return AdminSurveyListResponse(
            surveys=surveys,
            pagination=AdminSurveyPagination(total=total, limit=limit, offset=offset),
        )

    def _build_admin_survey_response(
        self,
        *,
        survey: Survey,
        owner_username: str,
        workspace_name: str,
        workspace_description: str | None,
        responses_count: int,
    ) -> AdminSurveyResponse:
        survey_url = self._survey_url(survey)
        return AdminSurveyResponse(
            id=survey.id,
            user_id=survey.user_id,
            owner_username=owner_username,
            workspace_id=survey.workspace_id,
            workspace_name=workspace_name,
            workspace_description=workspace_description,
            survey_link=survey_url,
            status="Active" if survey_url else "Closed",
            question_count=len(survey.questions or []),
            responses_count=responses_count,
            created_at=survey.created_at,
            updated_at=survey.updated_at,
        )

    async def list_survey_responses(
        self,
        db: AsyncSession,
        survey_id: int,
        limit: int,
        offset: int,
        search: str | None,
    ) -> AdminSurveyResponsesListResponse:
        """Return collected responses for any survey, restricted to administrators."""
        survey = await self._get_survey_or_404(db, survey_id)
        filters = [PublicSurveyResponse.survey_id == survey.id]
        if search:
            term = f"%{search.strip()}%"
            filters.append(
                or_(
                    PublicSurveyResponse.respondent_email.ilike(term),
                    cast(PublicSurveyResponse.id, String).ilike(term),
                    cast(PublicSurveyResponse.answers, String).ilike(term),
                )
            )

        total_statement = select(func.count(PublicSurveyResponse.id)).where(*filters)
        responses_statement = (
            select(PublicSurveyResponse)
            .where(*filters)
            .order_by(PublicSurveyResponse.submitted_at.desc(), PublicSurveyResponse.id.desc())
            .offset(offset)
            .limit(limit)
        )

        total = (await db.execute(total_statement)).scalar_one()
        responses = (await db.execute(responses_statement)).scalars().all()
        logger.info(
            "Admin survey responses fetched: survey_id=%s count=%s total=%s",
            survey.id, len(responses), total,
        )

        return AdminSurveyResponsesListResponse(
            survey_id=survey.id,
            survey_link=self._survey_url(survey),
            total_responses=total,
            responses=[self._build_response_item(response, survey) for response in responses],
            pagination=AdminSurveyResponsePagination(total=total, limit=limit, offset=offset),
        )

    async def get_survey_response_detail(
        self,
        db: AsyncSession,
        survey_id: int,
        response_id: int,
    ) -> AdminSurveyResponseDetailResponse:
        """Return one collected response for the admin response detail panel."""
        statement = (
            select(PublicSurveyResponse, Survey, User.username, Workspace.name, Workspace.description)
            .join(Survey, Survey.id == PublicSurveyResponse.survey_id)
            .join(User, User.id == Survey.user_id)
            .join(Workspace, Workspace.id == Survey.workspace_id)
            .where(Survey.id == survey_id, PublicSurveyResponse.id == response_id)
        )
        row = (await db.execute(statement)).one_or_none()
        if row is None:
            await self._get_survey_or_404(db, survey_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Survey response not found.",
            )

        response, survey, owner_username, workspace_name, workspace_description = row
        item = self._build_response_item(response, survey)
        return AdminSurveyResponseDetailResponse(
            **item.model_dump(),
            user_id=survey.user_id,
            owner_username=owner_username,
            workspace_id=survey.workspace_id,
            workspace_name=workspace_name,
            workspace_description=workspace_description,
            survey_link=self._survey_url(survey),
        )

    async def get_user_survey_summary(
        self, db: AsyncSession, user_id: int
    ) -> AdminUserSurveySummaryResponse:
        """Header summary for the admin 'user detail' page: name/email/status,
        joined date, and aggregate survey/response counts for one user."""
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        details = (
            await db.execute(select(UserDetails).where(UserDetails.user_id == user_id))
        ).scalar_one_or_none()
        name = f"{details.first_name} {details.last_name}".strip() if details else (
            user.display_name or user.username.split("@", 1)[0]
        )
        email = details.email if details else user.username
        user_status = details.profile_status if details else "Active"

        surveys_created = (
            await db.execute(select(func.count(Survey.id)).where(Survey.user_id == user_id))
        ).scalar_one()
        total_responses = (
            await db.execute(
                select(func.count(PublicSurveyResponse.id))
                .join(Survey, Survey.id == PublicSurveyResponse.survey_id)
                .where(Survey.user_id == user_id)
            )
        ).scalar_one()
        responses_subq = (
            select(
                PublicSurveyResponse.survey_id.label("survey_id"),
                func.count(PublicSurveyResponse.id).label("responses_count"),
            )
            .group_by(PublicSurveyResponse.survey_id)
            .subquery()
        )
        survey_rows = (
            await db.execute(
                select(
                    Survey,
                    Workspace.name,
                    Workspace.description,
                    func.coalesce(responses_subq.c.responses_count, 0),
                )
                .join(Workspace, Workspace.id == Survey.workspace_id)
                .outerjoin(responses_subq, responses_subq.c.survey_id == Survey.id)
                .where(Survey.user_id == user_id)
                .order_by(Survey.created_at.desc(), Survey.id.desc())
            )
        ).all()

        return AdminUserSurveySummaryResponse(
            user_id=user.id,
            name=name,
            email=email,
            status=user_status,
            joined_on=user.created_at,
            surveys_created=surveys_created,
            total_responses=total_responses,
            surveys=[
                self._build_user_survey_summary_item(
                    survey=survey,
                    workspace_name=workspace_name,
                    workspace_description=workspace_description,
                    responses_count=responses_count,
                )
                for survey, workspace_name, workspace_description, responses_count in survey_rows
            ],
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

    async def _get_survey_or_404(self, db: AsyncSession, survey_id: int) -> Survey:
        survey = (await db.execute(select(Survey).where(Survey.id == survey_id))).scalar_one_or_none()
        if survey is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Survey {survey_id} not found.",
            )
        return survey

    @staticmethod
    def _response_code(response_id: int) -> str:
        return f"#RS-{response_id:06d}"

    @staticmethod
    def _survey_url(survey: Survey) -> str | None:
        if survey.survey_link:
            return survey.survey_link

        base_url = os.getenv("PUBLIC_APP_URL")
        if not base_url or not survey.public_token:
            return None
        return f"{base_url.rstrip('/')}/surveys/public/{survey.public_token}"

    def _build_user_survey_summary_item(
        self,
        *,
        survey: Survey,
        workspace_name: str,
        workspace_description: str | None,
        responses_count: int,
    ) -> AdminUserSurveySummaryItem:
        survey_url = self._survey_url(survey)
        return AdminUserSurveySummaryItem(
            id=survey.id,
            workspace_id=survey.workspace_id,
            workspace_name=workspace_name,
            workspace_description=workspace_description,
            survey_link=survey_url,
            status="Active" if survey_url else "Closed",
            question_count=len(survey.questions or []),
            responses_count=responses_count,
            created_at=survey.created_at,
            updated_at=survey.updated_at,
        )

    def _build_response_item(
        self,
        response: PublicSurveyResponse,
        survey: Survey,
    ) -> AdminSurveyResponseItem:
        return AdminSurveyResponseItem(
            id=response.id,
            response_code=self._response_code(response.id),
            survey_id=response.survey_id,
            respondent_email=response.respondent_email,
            answers=response.answers or [],
            answers_preview=self._build_answers_preview(survey.questions or [], response.answers or []),
            submitted_at=response.submitted_at,
        )

    @staticmethod
    def _build_answers_preview(
        questions: list,
        answers: list,
    ) -> list[AdminSurveyAnswerPreviewItem]:
        question_lookup = {
            question.get("id"): question.get("question", f"Question {question.get('id')}")
            for question in questions
            if isinstance(question, dict)
        }
        preview: list[AdminSurveyAnswerPreviewItem] = []
        for answer in answers:
            if not isinstance(answer, dict):
                preview.append(
                    AdminSurveyAnswerPreviewItem(
                        question="Unknown question",
                        answer=answer,
                    )
                )
                continue

            question_id = answer.get("questionId")
            preview.append(
                AdminSurveyAnswerPreviewItem(
                    question=question_lookup.get(question_id, f"Question {question_id}"),
                    answer=answer.get("answer"),
                )
            )
        return preview

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
