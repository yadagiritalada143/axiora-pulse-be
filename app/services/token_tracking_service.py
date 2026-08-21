"""
app/services/token_tracking_service.py
────────────────────────────────────────────────────────────────────────────────
Centralized service for calculating, recording, and querying LLM token consumption
per user and per workspace.
"""
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TokenUsage, User, UserTokenTotal, Workspace
from app.models.token_models import (
    AdminTokenAnalyticsOut,
    AdminUserTokenUsage,
    DailyTokenUsage,
    ModelTokenBreakdown,
    SourceTokenBreakdown,
    TokenUsageLogOut,
    UserTokenSummaryOut,
    UserTokenTotalOut,
    WorkspaceTokenSummaryOut,
    WorkspaceUsageEntry,
)

logger = logging.getLogger(__name__)

# ── Model Pricing Rates (USD per 1,000,000 tokens) ────────────────────────────
# Maps prefix/model key to (prompt_cost_per_1m, completion_cost_per_1m)
MODEL_PRICING_PER_1M: Dict[str, tuple[float, float]] = {
    "gpt-5.4-mini": (0.15, 0.60),
    "gpt-5.4": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-haiku": (0.25, 1.25),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
    "llama-3.1-8b": (0.10, 0.10),
    "llama-3.1-70b": (0.60, 0.60),
}
DEFAULT_PRICING: tuple[float, float] = (0.15, 0.60)


class TokenTrackingService:
    """Service to track and analyze LLM token usage."""

    def calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate estimated cost in USD based on model rates."""
        normalized_model = (model or "").lower()
        pricing = DEFAULT_PRICING
        for model_key, rates in MODEL_PRICING_PER_1M.items():
            if model_key in normalized_model:
                pricing = rates
                break

        prompt_cost = (prompt_tokens / 1_000_000.0) * pricing[0]
        completion_cost = (completion_tokens / 1_000_000.0) * pricing[1]
        return round(prompt_cost + completion_cost, 6)

    async def record_usage(
        self,
        db: AsyncSession,
        user_id: int,
        source: str,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        workspace_id: Optional[int] = None,
        agent_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TokenUsage:
        """
        Persist a token usage log entry into the `token_usages` table.
        """
        prompt_tokens = max(0, int(prompt_tokens or 0))
        completion_tokens = max(0, int(completion_tokens or 0))
        total_tokens = prompt_tokens + completion_tokens
        estimated_cost = self.calculate_cost(model, prompt_tokens, completion_tokens)

        usage = TokenUsage(
            user_id=user_id,
            workspace_id=workspace_id,
            source=source,
            agent_name=agent_name,
            provider=provider or "openai",
            model=model or "gpt-5.4-mini",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost=estimated_cost,
            metadata_json=metadata or {},
            created_at=datetime.now(timezone.utc),
        )
        db.add(usage)

        # Upsert cumulative user totals (exactly 1 row per user)
        res = await db.execute(select(UserTokenTotal).where(UserTokenTotal.user_id == user_id))
        user_total = res.scalar_one_or_none()
        if user_total is None:
            user_total = UserTokenTotal(
                user_id=user_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                total_cost=estimated_cost,
                total_calls=1,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(user_total)
        else:
            user_total.prompt_tokens += prompt_tokens
            user_total.completion_tokens += completion_tokens
            user_total.total_tokens += total_tokens
            user_total.total_cost = round(user_total.total_cost + estimated_cost, 6)
            user_total.total_calls += 1
            user_total.updated_at = datetime.now(timezone.utc)

        await db.flush()

        logger.info(
            "[TokenTracking] Recorded %d tokens (%d in / %d out | $%.5f) for user_id=%s, workspace_id=%s, source=%s, model=%s (User total: %d tokens)",
            total_tokens,
            prompt_tokens,
            completion_tokens,
            estimated_cost,
            user_id,
            workspace_id,
            source,
            model,
            user_total.total_tokens,
        )
        return usage

    async def get_user_total(
        self,
        user_id: int,
        db: AsyncSession,
    ) -> UserTokenTotalOut:
        """
        Get the 1-row cumulative token total record for a user.
        If no record exists yet, initializes and returns a default 0-token total row.
        """
        res = await db.execute(select(UserTokenTotal).where(UserTokenTotal.user_id == user_id))
        user_total = res.scalar_one_or_none()
        if not user_total:
            user_total = UserTokenTotal(
                user_id=user_id,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                total_cost=0.0,
                total_calls=0,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(user_total)
            await db.flush()
        return UserTokenTotalOut.model_validate(user_total)

    async def get_workspace_summary(
        self,
        workspace_id: int,
        user_id: int,
        db: AsyncSession,
        limit_logs: int = 50,
    ) -> WorkspaceTokenSummaryOut:
        """
        Get aggregated token usage and breakdown for a given workspace.
        """
        # Overall totals
        total_query = select(
            func.coalesce(func.sum(TokenUsage.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(TokenUsage.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(TokenUsage.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(TokenUsage.estimated_cost), 0.0).label("estimated_cost"),
            func.count(TokenUsage.id).label("total_calls"),
        ).where(TokenUsage.workspace_id == workspace_id, TokenUsage.user_id == user_id)

        res = await db.execute(total_query)
        row = res.one()

        # Breakdown by source
        source_query = (
            select(
                TokenUsage.source,
                func.sum(TokenUsage.prompt_tokens).label("prompt_tokens"),
                func.sum(TokenUsage.completion_tokens).label("completion_tokens"),
                func.sum(TokenUsage.total_tokens).label("total_tokens"),
                func.sum(TokenUsage.estimated_cost).label("estimated_cost"),
                func.count(TokenUsage.id).label("call_count"),
            )
            .where(TokenUsage.workspace_id == workspace_id, TokenUsage.user_id == user_id)
            .group_by(TokenUsage.source)
        )
        source_res = await db.execute(source_query)
        by_source = [
            SourceTokenBreakdown(
                source=r.source,
                total_prompt_tokens=int(r.prompt_tokens or 0),
                total_completion_tokens=int(r.completion_tokens or 0),
                total_tokens=int(r.total_tokens or 0),
                estimated_cost=round(float(r.estimated_cost or 0.0), 6),
                call_count=int(r.call_count or 0),
            )
            for r in source_res.all()
        ]

        # Breakdown by model
        model_query = (
            select(
                TokenUsage.model,
                TokenUsage.provider,
                func.sum(TokenUsage.prompt_tokens).label("prompt_tokens"),
                func.sum(TokenUsage.completion_tokens).label("completion_tokens"),
                func.sum(TokenUsage.total_tokens).label("total_tokens"),
                func.sum(TokenUsage.estimated_cost).label("estimated_cost"),
                func.count(TokenUsage.id).label("call_count"),
            )
            .where(TokenUsage.workspace_id == workspace_id, TokenUsage.user_id == user_id)
            .group_by(TokenUsage.model, TokenUsage.provider)
        )
        model_res = await db.execute(model_query)
        by_model = [
            ModelTokenBreakdown(
                model=r.model,
                provider=r.provider,
                total_prompt_tokens=int(r.prompt_tokens or 0),
                total_completion_tokens=int(r.completion_tokens or 0),
                total_tokens=int(r.total_tokens or 0),
                estimated_cost=round(float(r.estimated_cost or 0.0), 6),
                call_count=int(r.call_count or 0),
            )
            for r in model_res.all()
        ]

        # Recent logs
        logs_query = (
            select(TokenUsage)
            .where(TokenUsage.workspace_id == workspace_id, TokenUsage.user_id == user_id)
            .order_by(TokenUsage.created_at.desc())
            .limit(limit_logs)
        )
        logs_res = await db.execute(logs_query)
        recent_logs = [TokenUsageLogOut.model_validate(log) for log in logs_res.scalars().all()]

        return WorkspaceTokenSummaryOut(
            workspace_id=workspace_id,
            total_prompt_tokens=int(row.prompt_tokens),
            total_completion_tokens=int(row.completion_tokens),
            total_tokens=int(row.total_tokens),
            estimated_cost=round(float(row.estimated_cost), 6),
            total_calls=int(row.total_calls),
            by_source=by_source,
            by_model=by_model,
            recent_logs=recent_logs,
        )

    async def get_user_summary(
        self,
        user_id: int,
        db: AsyncSession,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> UserTokenSummaryOut:
        """
        Get overall token usage metrics for a user, aggregated across all their workspaces.
        """
        filters = [TokenUsage.user_id == user_id]
        if start_date:
            filters.append(TokenUsage.created_at >= start_date)
        if end_date:
            filters.append(TokenUsage.created_at <= end_date)

        # Overall user totals
        total_query = select(
            func.coalesce(func.sum(TokenUsage.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(TokenUsage.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(TokenUsage.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(TokenUsage.estimated_cost), 0.0).label("estimated_cost"),
            func.count(TokenUsage.id).label("total_calls"),
        ).where(*filters)
        res = await db.execute(total_query)
        row = res.one()

        # Breakdown by workspace
        ws_query = (
            select(
                TokenUsage.workspace_id,
                Workspace.name.label("workspace_name"),
                func.sum(TokenUsage.prompt_tokens).label("prompt_tokens"),
                func.sum(TokenUsage.completion_tokens).label("completion_tokens"),
                func.sum(TokenUsage.total_tokens).label("total_tokens"),
                func.sum(TokenUsage.estimated_cost).label("estimated_cost"),
                func.count(TokenUsage.id).label("total_calls"),
            )
            .outerjoin(Workspace, TokenUsage.workspace_id == Workspace.id)
            .where(*filters)
            .group_by(TokenUsage.workspace_id, Workspace.name)
            .order_by(func.sum(TokenUsage.total_tokens).desc())
        )
        ws_res = await db.execute(ws_query)
        by_workspace = [
            WorkspaceUsageEntry(
                workspace_id=r.workspace_id,
                workspace_name=r.workspace_name or ("Non-workspace / Global" if r.workspace_id is None else f"Workspace #{r.workspace_id}"),
                total_prompt_tokens=int(r.prompt_tokens or 0),
                total_completion_tokens=int(r.completion_tokens or 0),
                total_tokens=int(r.total_tokens or 0),
                estimated_cost=round(float(r.estimated_cost or 0.0), 6),
                total_calls=int(r.total_calls or 0),
            )
            for r in ws_res.all()
        ]

        # Breakdown by source
        source_query = (
            select(
                TokenUsage.source,
                func.sum(TokenUsage.prompt_tokens).label("prompt_tokens"),
                func.sum(TokenUsage.completion_tokens).label("completion_tokens"),
                func.sum(TokenUsage.total_tokens).label("total_tokens"),
                func.sum(TokenUsage.estimated_cost).label("estimated_cost"),
                func.count(TokenUsage.id).label("call_count"),
            )
            .where(*filters)
            .group_by(TokenUsage.source)
        )
        source_res = await db.execute(source_query)
        by_source = [
            SourceTokenBreakdown(
                source=r.source,
                total_prompt_tokens=int(r.prompt_tokens or 0),
                total_completion_tokens=int(r.completion_tokens or 0),
                total_tokens=int(r.total_tokens or 0),
                estimated_cost=round(float(r.estimated_cost or 0.0), 6),
                call_count=int(r.call_count or 0),
            )
            for r in source_res.all()
        ]

        # Breakdown by model
        model_query = (
            select(
                TokenUsage.model,
                TokenUsage.provider,
                func.sum(TokenUsage.prompt_tokens).label("prompt_tokens"),
                func.sum(TokenUsage.completion_tokens).label("completion_tokens"),
                func.sum(TokenUsage.total_tokens).label("total_tokens"),
                func.sum(TokenUsage.estimated_cost).label("estimated_cost"),
                func.count(TokenUsage.id).label("call_count"),
            )
            .where(*filters)
            .group_by(TokenUsage.model, TokenUsage.provider)
        )
        model_res = await db.execute(model_query)
        by_model = [
            ModelTokenBreakdown(
                model=r.model,
                provider=r.provider,
                total_prompt_tokens=int(r.prompt_tokens or 0),
                total_completion_tokens=int(r.completion_tokens or 0),
                total_tokens=int(r.total_tokens or 0),
                estimated_cost=round(float(r.estimated_cost or 0.0), 6),
                call_count=int(r.call_count or 0),
            )
            for r in model_res.all()
        ]

        # Daily usage series (last 30 days)
        date_col = func.date(TokenUsage.created_at)
        daily_query = (
            select(
                date_col.label("usage_date"),
                func.sum(TokenUsage.total_tokens).label("total_tokens"),
                func.sum(TokenUsage.prompt_tokens).label("prompt_tokens"),
                func.sum(TokenUsage.completion_tokens).label("completion_tokens"),
                func.sum(TokenUsage.estimated_cost).label("estimated_cost"),
                func.count(TokenUsage.id).label("call_count"),
            )
            .where(*filters)
            .group_by(date_col)
            .order_by(date_col.asc())
        )
        daily_res = await db.execute(daily_query)
        daily_usage = [
            DailyTokenUsage(
                date=str(r.usage_date),
                total_tokens=int(r.total_tokens or 0),
                prompt_tokens=int(r.prompt_tokens or 0),
                completion_tokens=int(r.completion_tokens or 0),
                estimated_cost=round(float(r.estimated_cost or 0.0), 6),
                call_count=int(r.call_count or 0),
            )
            for r in daily_res.all()
        ]

        return UserTokenSummaryOut(
            user_id=user_id,
            total_prompt_tokens=int(row.prompt_tokens),
            total_completion_tokens=int(row.completion_tokens),
            total_tokens=int(row.total_tokens),
            estimated_cost=round(float(row.estimated_cost), 6),
            total_calls=int(row.total_calls),
            by_workspace=by_workspace,
            by_source=by_source,
            by_model=by_model,
            daily_usage=daily_usage,
        )

    async def get_admin_analytics(
        self,
        db: AsyncSession,
        top_n: int = 20,
    ) -> AdminTokenAnalyticsOut:
        """
        Platform-wide token analytics for administrators.
        """
        # Overall platform totals
        total_query = select(
            func.coalesce(func.sum(TokenUsage.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(TokenUsage.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(TokenUsage.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(TokenUsage.estimated_cost), 0.0).label("estimated_cost"),
            func.count(TokenUsage.id).label("total_calls"),
        )
        res = await db.execute(total_query)
        row = res.one()

        # Top token-consuming users
        top_users_query = (
            select(
                TokenUsage.user_id,
                User.username,
                func.sum(TokenUsage.total_tokens).label("total_tokens"),
                func.sum(TokenUsage.prompt_tokens).label("prompt_tokens"),
                func.sum(TokenUsage.completion_tokens).label("completion_tokens"),
                func.sum(TokenUsage.estimated_cost).label("estimated_cost"),
                func.count(TokenUsage.id).label("total_calls"),
            )
            .join(User, TokenUsage.user_id == User.id)
            .group_by(TokenUsage.user_id, User.username)
            .order_by(func.sum(TokenUsage.total_tokens).desc())
            .limit(top_n)
        )
        top_users_res = await db.execute(top_users_query)
        top_users = [
            AdminUserTokenUsage(
                user_id=r.user_id,
                username=r.username,
                total_tokens=int(r.total_tokens or 0),
                prompt_tokens=int(r.prompt_tokens or 0),
                completion_tokens=int(r.completion_tokens or 0),
                estimated_cost=round(float(r.estimated_cost or 0.0), 6),
                total_calls=int(r.total_calls or 0),
            )
            for r in top_users_res.all()
        ]

        # By model
        model_query = (
            select(
                TokenUsage.model,
                TokenUsage.provider,
                func.sum(TokenUsage.prompt_tokens).label("prompt_tokens"),
                func.sum(TokenUsage.completion_tokens).label("completion_tokens"),
                func.sum(TokenUsage.total_tokens).label("total_tokens"),
                func.sum(TokenUsage.estimated_cost).label("estimated_cost"),
                func.count(TokenUsage.id).label("call_count"),
            )
            .group_by(TokenUsage.model, TokenUsage.provider)
            .order_by(func.sum(TokenUsage.total_tokens).desc())
        )
        model_res = await db.execute(model_query)
        by_model = [
            ModelTokenBreakdown(
                model=r.model,
                provider=r.provider,
                total_prompt_tokens=int(r.prompt_tokens or 0),
                total_completion_tokens=int(r.completion_tokens or 0),
                total_tokens=int(r.total_tokens or 0),
                estimated_cost=round(float(r.estimated_cost or 0.0), 6),
                call_count=int(r.call_count or 0),
            )
            for r in model_res.all()
        ]

        # By source
        source_query = (
            select(
                TokenUsage.source,
                func.sum(TokenUsage.prompt_tokens).label("prompt_tokens"),
                func.sum(TokenUsage.completion_tokens).label("completion_tokens"),
                func.sum(TokenUsage.total_tokens).label("total_tokens"),
                func.sum(TokenUsage.estimated_cost).label("estimated_cost"),
                func.count(TokenUsage.id).label("call_count"),
            )
            .group_by(TokenUsage.source)
            .order_by(func.sum(TokenUsage.total_tokens).desc())
        )
        source_res = await db.execute(source_query)
        by_source = [
            SourceTokenBreakdown(
                source=r.source,
                total_prompt_tokens=int(r.prompt_tokens or 0),
                total_completion_tokens=int(r.completion_tokens or 0),
                total_tokens=int(r.total_tokens or 0),
                estimated_cost=round(float(r.estimated_cost or 0.0), 6),
                call_count=int(r.call_count or 0),
            )
            for r in source_res.all()
        ]

        return AdminTokenAnalyticsOut(
            total_platform_tokens=int(row.total_tokens),
            total_platform_prompt_tokens=int(row.prompt_tokens),
            total_platform_completion_tokens=int(row.completion_tokens),
            total_platform_cost=round(float(row.estimated_cost), 6),
            total_platform_calls=int(row.total_calls),
            top_users=top_users,
            by_model=by_model,
            by_source=by_source,
        )


token_tracking_service = TokenTrackingService()
