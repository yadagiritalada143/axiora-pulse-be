"""Read-only administrator operations."""

import logging
import os
from datetime import datetime, timezone, timedelta

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import HTTPException, status

from app.db.models import (
    Payment,
    Plan,
    PublicSurveyResponse,
    Role,
    Subscription,
    Survey,
    User,
    UserDetails,
    Workspace,
)
from app.models.admin_models import (
    AdminDashboardGrowth,
    AdminDashboardStatsResponse,
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
    RevenueDataPoint,
    RevenueResponse,
    UserGrowthAnalyticsResponse,
    UserGrowthDataPoint,
    UserGrowthPoint,
    UserGrowthResponse,
    UsersByPlanItem,
    UsersByPlanResponse,
)

logger = logging.getLogger(__name__)

# Subscription statuses that grant paid entitlement (mirrors billing_service).
# Only a webhook-confirmed 'active' subscription is treated as paid.
_ENTITLED = {"active"}
# Payment statuses considered successfully completed for revenue aggregation.
_SUCCESSFUL_PAYMENTS = {"captured"}


class AdminService:
    async def list_users(
        self,
        db: AsyncSession,
        limit: int,
        offset: int,
        search: str | None,
    ) -> AdminUserListResponse:
        """Return a paginated user directory (excluding admins) with workspace counts."""
        filters = [User.role_id != 1]  # exclude admin users
        if search:
            term = f"%{search.strip()}%"
            filters.append(or_(User.username.ilike(term), User.display_name.ilike(term)))

        # Subquery: per-user workspace counts split by is_delete
        ws_counts = (
            select(
                Workspace.user_id,
                func.count(Workspace.id).label("total"),
                func.count(Workspace.id).filter(Workspace.is_delete == False).label("active"),
                func.count(Workspace.id).filter(Workspace.is_delete == True).label("archived"),
            )
            .group_by(Workspace.user_id)
            .subquery()
        )

        total_statement = select(func.count(User.id)).where(*filters)

        users_statement = (
            select(
                User,
                func.coalesce(ws_counts.c.total, 0).label("workspace_count"),
                func.coalesce(ws_counts.c.active, 0).label("active_workspace_count"),
                func.coalesce(ws_counts.c.archived, 0).label("archived_workspace_count"),
            )
            .outerjoin(ws_counts, ws_counts.c.user_id == User.id)
            .where(*filters)
            .order_by(User.created_at.desc(), User.id.desc())
            .offset(offset)
            .limit(limit)
        )

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
                role=user._primary_role,
                created_at=user.created_at,
                workspace_count=workspace_count,
                active_workspace_count=active_workspace_count,
                archived_workspace_count=archived_workspace_count,
            )
            for user, workspace_count, active_workspace_count, archived_workspace_count in rows
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

    # ── Dashboard aggregation ─────────────────────────────────────────────────

    async def get_dashboard_stats(self, db: AsyncSession) -> AdminDashboardStatsResponse:
        """Return headline counts plus week-over-week growth for the dashboard.

        Customer metrics (users, workspaces) exclude admin accounts, matching the
        admin user directory. Growth is the percentage change of new records in
        the last 7 days versus the 7 days before that.
        """
        non_admin = User.role_id != 1
        user_base = select(func.count()).select_from(User)
        subs_base = (
            select(func.count())
            .select_from(Subscription)
            .join(User, User.id == Subscription.user_id)
        )
        ws_base = (
            select(func.count())
            .select_from(Workspace)
            .join(User, User.id == Workspace.user_id)
        )

        total_users = await self._count_where(db, user_base, non_admin)
        paid_users = await self._count(
            db,
            select(func.count(func.distinct(Subscription.user_id)))
            .select_from(Subscription)
            .join(User, User.id == Subscription.user_id)
            .where(Subscription.status.in_(_ENTITLED), non_admin),
        )
        active_subscriptions = await self._count_where(
            db, subs_base, Subscription.status.in_(_ENTITLED), non_admin
        )
        total_workspaces = await self._count_where(db, ws_base, non_admin)
        active_workspaces = await self._count_where(
            db, ws_base, Workspace.is_delete == False, non_admin
        )
        archived_workspaces = await self._count_where(
            db, ws_base, Workspace.is_delete == True, non_admin
        )

        users_cur, users_prev = await self._window_counts(db, user_base, User.created_at, non_admin)
        paid_cur, paid_prev = await self._window_counts(
            db, subs_base, Subscription.created_at, Subscription.status.in_(_ENTITLED), non_admin
        )
        workspaces_cur, workspaces_prev = await self._window_counts(
            db, ws_base, Workspace.created_at, non_admin
        )
        active_ws_cur, active_ws_prev = await self._window_counts(
            db, ws_base, Workspace.created_at, Workspace.is_delete == False, non_admin
        )
        archived_ws_cur, archived_ws_prev = await self._window_counts(
            db, ws_base, Workspace.created_at, Workspace.is_delete == True, non_admin
        )

        nonpaid_cur = max(users_cur - paid_cur, 0)
        nonpaid_prev = max(users_prev - paid_prev, 0)

        logger.info(
            "Admin dashboard stats: users=%s paid=%s active_subs=%s workspaces=%s (active=%s, archived=%s)",
            total_users, paid_users, active_subscriptions, total_workspaces,
            active_workspaces, archived_workspaces,
        )

        return AdminDashboardStatsResponse(
            total_users=total_users,
            paid_users=paid_users,
            non_paid_users=max(total_users - paid_users, 0),
            active_subscriptions=active_subscriptions,
            total_workspaces=total_workspaces,
            active_workspaces=active_workspaces,
            archived_workspaces=archived_workspaces,
            growth=AdminDashboardGrowth(
                total_users=_growth_pct(users_cur, users_prev),
                paid_users=_growth_pct(paid_cur, paid_prev),
                non_paid_users=_growth_pct(nonpaid_cur, nonpaid_prev),
                active_subscriptions=_growth_pct(paid_cur, paid_prev),
                total_workspaces=_growth_pct(workspaces_cur, workspaces_prev),
                active_workspaces=_growth_pct(active_ws_cur, active_ws_prev),
                archived_workspaces=_growth_pct(archived_ws_cur, archived_ws_prev),
            ),
        )

    @staticmethod
    async def _count(db: AsyncSession, statement) -> int:
        return (await db.execute(statement)).scalar_one()

    @staticmethod
    async def _count_where(db: AsyncSession, base_stmt, *filters) -> int:
        """Count rows using ``base_stmt`` (a count SELECT) with extra filters."""
        stmt = base_stmt
        if filters:
            stmt = stmt.where(*filters)
        return (await db.execute(stmt)).scalar_one()

    async def _window_counts(
        self, db: AsyncSession, base_stmt, column, *filters
    ) -> tuple[int, int]:
        """Return (current_7d, previous_7d) counts of rows matching ``filters``.

        Current window is (now-7d, now]; previous window is (now-14d, now-7d].
        Uses naive-UTC now so SQLite datetime string comparisons align with the
        ``datetime.utcnow``-stored created_at values.
        """
        now = datetime.utcnow()
        cur_start = now - timedelta(days=7)
        prev_start = now - timedelta(days=14)
        current = await self._count_where(
            db, base_stmt, column > cur_start, column <= now, *filters
        )
        previous = await self._count_where(
            db, base_stmt, column > prev_start, column <= cur_start, *filters
        )
        return current, previous

    # ── User growth (date-bucketed) ───────────────────────────────────────────

    async def get_user_growth_analytics(
        self, db: AsyncSession, period: str
    ) -> UserGrowthAnalyticsResponse:
        """Return registration counts bucketed by date for the given period.

        ``period`` is one of week | month | last_7_days | last_30_days | year.
        Day buckets are labelled ``YYYY-MM-DD``; month buckets ``YYYY-MM``.
        Sparse buckets are zero-filled so the series is continuous.
        """
        now = datetime.utcnow()
        granularity, start = self._period_window(period, now)
        period_expr = self._period_expr(db, "day" if granularity == "day" else "month", User.created_at)

        statement = (
            select(period_expr.label("period"), func.count(User.id).label("count"))
            .where(User.created_at >= start, User.role_id != 1)
            .group_by(period_expr)
            .order_by(period_expr)
        )
        rows = (await db.execute(statement)).all()
        counts = {row.period: row.count for row in rows}

        labels = self._series_labels(granularity, start, now)
        series = [
            UserGrowthDataPoint(period=label, count=counts.get(label, 0)) for label in labels
        ]
        logger.info("Admin user-growth analytics: period=%s buckets=%s", period, len(series))
        return UserGrowthAnalyticsResponse(period=period, series=series)

    # ── Users by plan ────────────────────────────────────────────────────────

    async def get_users_by_plan(self, db: AsyncSession) -> UsersByPlanResponse:
        """Return the number of users per subscription plan and their share.

        A user's plan is the plan of their most recently created subscription;
        users with no subscription are counted under the ``free`` plan.
        """
        plan_rows = (
            await db.execute(select(Plan).order_by(Plan.tier, Plan.id))
        ).scalars().all()
        plan_by_id = {p.id: p for p in plan_rows}
        total_users = await self._count_where(
            db, select(func.count()).select_from(User), User.role_id != 1
        )

        entitled_rows = (
            await db.execute(
                select(Subscription.user_id, Subscription.plan_id, Subscription.created_at)
                .join(User, User.id == Subscription.user_id)
                .where(Subscription.status.in_(_ENTITLED), User.role_id != 1)
                .order_by(Subscription.user_id, Subscription.created_at.desc(), Subscription.id.desc())
            )
        ).all()

        latest_by_user: dict[int, Subscription] = {}
        for user_id, plan_id, created_at in entitled_rows:
            latest_by_user.setdefault(user_id, plan_id)

        plan_counts: dict[str, int] = {}
        for plan in plan_by_id.values():
            plan_counts[plan.code] = 0
        for user_id, plan_id in latest_by_user.items():
            if plan_id is not None and plan_id in plan_by_id:
                plan_counts[plan_by_id[plan_id].code] += 1
            else:
                plan_counts["free"] = plan_counts.get("free", 0) + 1
        # Users with no entitled subscription are on the free plan.
        paid_user_ids = set(latest_by_user.keys())
        free_count = total_users - len(paid_user_ids)
        plan_counts["free"] = plan_counts.get("free", 0) + free_count

        plans = [
            UsersByPlanItem(
                plan=code,
                user_count=count,
                percentage=round((count / total_users) * 100, 1) if total_users else 0.0,
            )
            for code, count in plan_counts.items()
            if count > 0
        ]
        logger.info("Admin users-by-plan: total=%s plans=%s", total_users, len(plans))
        return UsersByPlanResponse(total_users=total_users, plans=plans)

    # ── Revenue ──────────────────────────────────────────────────────────────

    async def get_revenue(self, db: AsyncSession, period: str) -> RevenueResponse:
        """Return successful payment revenue aggregated over ``period``.

        ``today`` buckets hourly, ``week``/``month`` daily, ``year`` monthly.
        Only payments whose status is in ``_SUCCESSFUL_PAYMENTS`` are included.
        """
        now = datetime.utcnow()
        granularity, start = self._period_window(period, now)
        period_expr = self._period_expr(db, granularity, Payment.created_at)

        rows = (
            await db.execute(
                select(
                    period_expr.label("period"),
                    func.sum(Payment.amount).label("total_paise"),
                )                .where(Payment.status.in_(_SUCCESSFUL_PAYMENTS), Payment.created_at >= start)
                .group_by(period_expr)
                .order_by(period_expr)
            )
        ).all()
        sums = {row.period: (row.total_paise or 0) / 100.0 for row in rows}

        labels = self._series_labels(granularity, start, now)
        series = [
            RevenueDataPoint(period=label, amount=sums.get(label, 0.0)) for label in labels
        ]
        total_amount = round(sum(point.amount for point in series), 2)
        logger.info("Admin revenue: period=%s total=%.2f buckets=%s", period, total_amount, len(series))
        return RevenueResponse(period=period, total_amount=total_amount, series=series)

    # ── Period helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _period_window(period: str, now: datetime) -> tuple[str, datetime]:
        """Map an analytics period to (granularity, inclusive start datetime).

        ``granularity`` is one of ``hour`` | ``day`` | ``month``.
        """
        if period == "today":
            return "hour", now.replace(hour=0, minute=0, second=0, microsecond=0)
        if period == "year":
            return "month", datetime(now.year, 1, 1)
        if period in ("week", "last_7_days"):
            return "day", now - timedelta(days=6)
        if period in ("month", "last_30_days"):
            return "day", now - timedelta(days=29)
        raise ValueError(f"Unsupported period: {period}")

    @staticmethod
    def _period_expr(db: AsyncSession, granularity: str, column):
        """Build a SQL expression formatting ``column`` into a period label.

        Granularity is one of ``hour`` | ``day`` | ``month``.
        """
        dialect = db.bind.dialect.name
        if dialect == "sqlite":
            if granularity == "hour":
                return func.strftime("%Y-%m-%d %H:00", column)
            fmt = "%Y-%m-%d" if granularity == "day" else "%Y-%m"
            return func.strftime(fmt, column)
        if granularity == "hour":
            return func.to_char(column, "YYYY-MM-DD HH24:00")
        fmt = "YYYY-MM-DD" if granularity == "day" else "YYYY-MM"
        return func.to_char(column, fmt)

    @staticmethod
    def _series_labels(granularity: str, start: datetime, now: datetime) -> list[str]:
        """Yield every period label from ``start`` through ``now`` inclusive."""
        if granularity == "hour":
            labels: list[str] = []
            cursor = datetime(start.year, start.month, start.day, start.hour)
            while cursor <= now:
                labels.append(cursor.strftime("%Y-%m-%d %H:00"))
                cursor += timedelta(hours=1)
            return labels
        if granularity == "month":
            labels = []
            year, month = start.year, start.month
            while (year, month) <= (now.year, now.month):
                labels.append(f"{year:04d}-{month:02d}")
                month += 1
                if month > 12:
                    month = 1
                    year += 1
            return labels
        labels = []
        cursor = start.date()
        end = now.date()
        while cursor <= end:
            labels.append(cursor.strftime("%Y-%m-%d"))
            cursor += timedelta(days=1)
        return labels


def _growth_pct(current: int, previous: int) -> float:
    """Percentage change of ``current`` versus ``previous``.

    When ``previous`` is zero the change is reported as 100 for any current
    growth, else 0.
    """
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round((current - previous) / previous * 100, 1)


admin_service = AdminService()
