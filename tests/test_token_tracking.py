"""
backend/tests/test_token_tracking.py
────────────────────────────────────────────────────────────────────────────────
Tests for token tracking model, token service, and analytics endpoints.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.models import TokenUsage, User, Workspace
from app.services.token_tracking_service import token_tracking_service
from main import app


@pytest.mark.asyncio
async def test_calculate_cost_gpt_5_4_mini():
    """Verify cost calculation for GPT-5.4-mini and other models."""
    # 1,000,000 prompt tokens ($0.15) + 1,000,000 completion tokens ($0.60) = $0.75
    cost = token_tracking_service.calculate_cost("gpt-5.4-mini", 1_000_000, 1_000_000)
    assert cost == 0.75

    # 10,000 prompt tokens + 2,000 completion tokens
    # (10000 / 1e6) * 0.15 = 0.0015
    # (2000 / 1e6) * 0.60 = 0.0012
    # Total = 0.0027
    cost_small = token_tracking_service.calculate_cost("gpt-5.4-mini", 10_000, 2_000)
    assert cost_small == 0.0027


@pytest.mark.asyncio
async def test_record_usage_and_fetch_summaries(db_session: AsyncSession, normal_user: User):
    """Test recording token usage and computing user & workspace summaries."""
    # 1. Create a workspace
    ws = Workspace(
        user_id=normal_user.id,
        name="Fintech AI App",
        description="A fintech venture",
        state="GATHERING_INFO",
    )
    db_session.add(ws)
    await db_session.commit()
    await db_session.refresh(ws)

    # 2. Record mentor chat tokens
    usage1 = await token_tracking_service.record_usage(
        db=db_session,
        user_id=normal_user.id,
        workspace_id=ws.id,
        source="mentor_chat",
        agent_name="ai_mentor",
        provider="openai",
        model="gpt-5.4-mini",
        prompt_tokens=1200,
        completion_tokens=300,
        metadata={"step": "greeting"},
    )
    assert usage1.id is not None
    assert usage1.total_tokens == 1500

    # 3. Record idea extraction tokens
    usage2 = await token_tracking_service.record_usage(
        db=db_session,
        user_id=normal_user.id,
        workspace_id=ws.id,
        source="idea_extraction",
        agent_name="idea_extractor",
        provider="openai",
        model="gpt-5.4-mini",
        prompt_tokens=800,
        completion_tokens=150,
    )
    assert usage2.total_tokens == 950
    await db_session.commit()

    # 4. Fetch Workspace Summary
    ws_summary = await token_tracking_service.get_workspace_summary(
        workspace_id=ws.id,
        user_id=normal_user.id,
        db=db_session,
    )
    assert ws_summary.workspace_id == ws.id
    assert ws_summary.total_tokens == 2450
    assert ws_summary.total_prompt_tokens == 2000
    assert ws_summary.total_completion_tokens == 450
    assert ws_summary.total_calls == 2
    assert len(ws_summary.by_source) == 2
    assert len(ws_summary.recent_logs) == 2

    # 5. Fetch User Summary
    user_summary = await token_tracking_service.get_user_summary(
        user_id=normal_user.id,
        db=db_session,
    )
    assert user_summary.user_id == normal_user.id
    assert user_summary.total_tokens == 2450
    assert len(user_summary.by_workspace) == 1
    assert user_summary.by_workspace[0].workspace_id == ws.id
    assert user_summary.by_workspace[0].total_tokens == 2450

    # 6. Verify 1-row UserTokenTotal
    user_total = await token_tracking_service.get_user_total(
        user_id=normal_user.id,
        db=db_session,
    )
    assert user_total is not None
    assert user_total.user_id == normal_user.id
    assert user_total.prompt_tokens == 2000
    assert user_total.completion_tokens == 450
    assert user_total.total_tokens == 2450
    assert user_total.total_calls == 2


@pytest.mark.asyncio
async def test_analytics_api_endpoints(
    client: AsyncClient,
    db_session: AsyncSession,
    normal_user: User,
    admin_user: User,
):
    """Test the analytics HTTP API routes."""
    # Create workspace and seed usage
    ws = Workspace(
        user_id=normal_user.id,
        name="Healthcare AI",
        description="Health diagnostics platform",
        state="GATHERING_INFO",
    )
    db_session.add(ws)
    await db_session.commit()
    await db_session.refresh(ws)

    await token_tracking_service.record_usage(
        db=db_session,
        user_id=normal_user.id,
        workspace_id=ws.id,
        source="agent_execution",
        agent_name="market_research_agent",
        provider="openai",
        model="gpt-5.4-mini",
        prompt_tokens=5000,
        completion_tokens=1000,
    )
    await db_session.commit()

    # Authenticate as normal_user
    app.dependency_overrides[get_current_user] = lambda: normal_user

    # GET /api/v1/analytics/tokens/me
    resp_me = await client.get("/api/v1/analytics/tokens/me")
    assert resp_me.status_code == 200
    me_data = resp_me.json()
    assert me_data["success"] is True
    assert me_data["data"]["total_tokens"] == 6000
    assert me_data["data"]["total_prompt_tokens"] == 5000
    assert me_data["data"]["total_completion_tokens"] == 1000

    # GET /api/v1/analytics/tokens/totals/me (1-row cumulative totals)
    resp_totals = await client.get("/api/v1/analytics/tokens/totals/me")
    assert resp_totals.status_code == 200
    totals_data = resp_totals.json()
    assert totals_data["success"] is True
    assert totals_data["data"]["user_id"] == normal_user.id
    assert totals_data["data"]["prompt_tokens"] == 5000
    assert totals_data["data"]["completion_tokens"] == 1000
    assert totals_data["data"]["total_tokens"] == 6000
    assert totals_data["data"]["total_calls"] == 1

    # GET /api/v1/analytics/tokens/workspaces/{workspace_id}
    resp_ws = await client.get(f"/api/v1/analytics/tokens/workspaces/{ws.id}")
    assert resp_ws.status_code == 200
    ws_data = resp_ws.json()
    assert ws_data["success"] is True
    assert ws_data["data"]["workspace_id"] == ws.id
    assert ws_data["data"]["total_tokens"] == 6000
    assert len(ws_data["data"]["recent_logs"]) == 1

    # Attempt to view admin route as normal_user -> 403 Forbidden
    resp_admin_forbidden = await client.get("/api/v1/analytics/admin/tokens")
    assert resp_admin_forbidden.status_code == 403

    # Authenticate as admin_user
    app.dependency_overrides[get_current_user] = lambda: admin_user
    resp_admin = await client.get("/api/v1/analytics/admin/tokens")
    assert resp_admin.status_code == 200
    admin_data = resp_admin.json()
    assert admin_data["success"] is True
    assert admin_data["data"]["total_platform_tokens"] >= 6000
