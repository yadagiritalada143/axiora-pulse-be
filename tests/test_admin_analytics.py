from datetime import datetime, timedelta

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.security import hash_password_async
from app.db.models import Payment, Plan, Role, Subscription, User, Workspace


# ── helpers ──────────────────────────────────────────────────────────────

async def create_user(
    db_session: AsyncSession,
    *,
    username: str,
    role: str = "viewer",
    created_at: datetime | None = None,
) -> User:
    role_obj = (await db_session.execute(select(Role).where(Role.name == role))).scalar_one_or_none()
    if role_obj is None:
        role_obj = Role(name=role, description=f"{role} role")
        db_session.add(role_obj)
        await db_session.flush()
    user = User(
        username=username,
        password=await hash_password_async("Test@12345"),
        register_mfa=True,
        role=role_obj,
    )
    if created_at is not None:
        user.created_at = created_at
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def create_workspace(
    db_session: AsyncSession,
    *,
    user_id: int,
    name: str,
    is_delete: bool = False,
    created_at: datetime | None = None,
) -> Workspace:
    workspace = Workspace(
        user_id=user_id,
        name=name,
        state="GATHERING_INFO",
        idea={},
        conversation_history=[],
        validation_result=None,
        is_delete=is_delete,
    )
    if created_at is not None:
        workspace.created_at = created_at
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)
    return workspace


async def create_plan(db_session: AsyncSession, *, code: str, name: str, tier: int = 1) -> Plan:
    plan = Plan(code=code, name=name, tier=tier)
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)
    return plan


async def create_subscription(
    db_session: AsyncSession,
    *,
    user_id: int,
    plan_id: int | None = None,
    status_name: str = "active",
    created_at: datetime | None = None,
) -> Subscription:
    sub = Subscription(
        user_id=user_id,
        plan_id=plan_id,
        razorpay_subscription_id=f"sub_{user_id}_{status_name}",
        razorpay_plan_id="rzp_plan_pro",
        billing_period="monthly",
        status=status_name,
    )
    if created_at is not None:
        sub.created_at = created_at
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    return sub


async def create_payment(
    db_session: AsyncSession,
    *,
    user_id: int | None,
    amount_paise: int,
    status_name: str = "captured",
    created_at: datetime | None = None,
) -> Payment:
    payment = Payment(
        user_id=user_id,
        razorpay_payment_id=f"pay_{status_name}_{amount_paise}_{id(object())}",
        amount=amount_paise,
        currency="INR",
        status=status_name,
    )
    if created_at is not None:
        payment.created_at = created_at
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)
    return payment


def authenticate_as(user: User) -> None:
    role_name = user._primary_role

    def _has_role(name: str) -> bool:
        return role_name == name

    from types import SimpleNamespace
    from main import app

    current_user = SimpleNamespace(id=user.id, username=user.username, role=role_name, has_role=_has_role)

    async def _mock_current_user():
        return current_user

    app.dependency_overrides[get_current_user] = _mock_current_user


# ── dashboard/stats ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dashboard_stats_requires_admin(client: AsyncClient, db_session: AsyncSession):
    user = await create_user(db_session, username="ds-nonadmin@axiorapulse.com")
    authenticate_as(user)
    response = await client.get("/api/v1/admin/dashboard/stats")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_dashboard_stats_returns_counts_and_growth(
    client: AsyncClient, db_session: AsyncSession
):
    now = datetime.utcnow()
    current = now - timedelta(days=1)
    previous = now - timedelta(days=9)
    old = now - timedelta(days=30)

    admin = await create_user(db_session, username="ds-admin@axiorapulse.com", role="admin", created_at=old)

    c1 = await create_user(db_session, username="ds-c1@axiorapulse.com", created_at=current)
    c2 = await create_user(db_session, username="ds-c2@axiorapulse.com", created_at=current)
    p1 = await create_user(db_session, username="ds-p1@axiorapulse.com", created_at=previous)
    p2 = await create_user(db_session, username="ds-p2@axiorapulse.com", created_at=previous)
    p3 = await create_user(db_session, username="ds-p3@axiorapulse.com", created_at=previous)

    await create_subscription(db_session, user_id=c1.id, status_name="active", created_at=current)
    await create_subscription(db_session, user_id=p1.id, status_name="active", created_at=previous)
    await create_subscription(db_session, user_id=p2.id, status_name="cancelled", created_at=previous)

    # user workspaces: active current=2, active previous=1, archived previous=1
    await create_workspace(db_session, user_id=c1.id, name="A-cur1", created_at=current)
    await create_workspace(db_session, user_id=c2.id, name="A-cur2", created_at=current)
    await create_workspace(db_session, user_id=p1.id, name="A-prev", created_at=previous)
    await create_workspace(db_session, user_id=p2.id, name="Arch-prev", is_delete=True, created_at=previous)

    authenticate_as(admin)
    response = await client.get("/api/v1/admin/dashboard/stats")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["total_users"] == 5  # admin excluded from customer counts
    assert data["paid_users"] == 2  # c1 + p1
    assert data["non_paid_users"] == 3
    assert data["active_subscriptions"] == 2  # both active
    assert data["total_workspaces"] == 4
    assert data["active_workspaces"] == 3
    assert data["archived_workspaces"] == 1

    g = data["growth"]
    assert g["total_users"] == -33.3  # (2-3)/3
    assert g["paid_users"] == 0.0  # 1 vs 1
    assert g["non_paid_users"] == -50.0  # (1-2)/2
    assert g["active_subscriptions"] == 0.0
    assert g["total_workspaces"] == 0.0  # 2 vs 2
    assert g["active_workspaces"] == 100.0  # 2 vs 1
    assert g["archived_workspaces"] == -100.0  # 0 vs 1


@pytest.mark.asyncio
async def test_dashboard_stats_empty(client: AsyncClient, db_session: AsyncSession):
    admin = await create_user(db_session, username="ds-empty-admin@axiorapulse.com", role="admin")
    authenticate_as(admin)
    response = await client.get("/api/v1/admin/dashboard/stats")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    # Admin accounts are excluded from customer metrics.
    assert data["total_users"] == 0
    assert data["paid_users"] == 0
    assert data["non_paid_users"] == 0
    assert data["total_workspaces"] == 0
    assert data["growth"]["total_users"] == 0.0


# ── analytics/user-growth ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_user_growth_requires_admin(client: AsyncClient, db_session: AsyncSession):
    user = await create_user(db_session, username="ug-nonadmin@axiorapulse.com")
    authenticate_as(user)
    response = await client.get("/api/v1/admin/analytics/user-growth")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_user_growth_last_7_days_daily(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_user(db_session, username="ug-admin@axiorapulse.com", role="admin")
    now = datetime.utcnow()
    await create_user(db_session, username="ug-today@axiorapulse.com", created_at=now)
    await create_user(db_session, username="ug-2d@axiorapulse.com", created_at=now - timedelta(days=2))

    authenticate_as(admin)
    response = await client.get(
        "/api/v1/admin/analytics/user-growth", params={"period": "last_7_days"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["period"] == "last_7_days"
    series = data["series"]
    assert len(series) == 7
    counts = {p["period"]: p["count"] for p in series}
    assert counts.get(now.strftime("%Y-%m-%d")) == 1
    assert counts.get((now - timedelta(days=2)).strftime("%Y-%m-%d")) == 1


@pytest.mark.asyncio
async def test_user_growth_year_monthly(client: AsyncClient, db_session: AsyncSession):
    admin = await create_user(db_session, username="ug-year@axiorapulse.com", role="admin")
    now = datetime.utcnow()
    await create_user(db_session, username="ug-y1@axiorapulse.com", created_at=now)

    authenticate_as(admin)
    response = await client.get(
        "/api/v1/admin/analytics/user-growth", params={"period": "year"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["period"] == "year"
    buckets = [p["period"] for p in data["series"]]
    assert len(set(buckets)) == len(buckets)
    assert now.strftime("%Y-%m") in buckets


@pytest.mark.asyncio
async def test_user_growth_rejects_invalid_period(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_user(db_session, username="ug-invalid@axiorapulse.com", role="admin")
    authenticate_as(admin)
    response = await client.get(
        "/api/v1/admin/analytics/user-growth", params={"period": "decade"}
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ── analytics/users-by-plan ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_users_by_plan_requires_admin(client: AsyncClient, db_session: AsyncSession):
    user = await create_user(db_session, username="ubp-nonadmin@axiorapulse.com")
    authenticate_as(user)
    response = await client.get("/api/v1/admin/analytics/users-by-plan")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_users_by_plan_distribution(client: AsyncClient, db_session: AsyncSession):
    admin = await create_user(db_session, username="ubp-admin@axiorapulse.com", role="admin")
    pro = await create_plan(db_session, code="pro", name="Pro", tier=1)
    ent = await create_plan(db_session, code="enterprise", name="Enterprise", tier=2)

    for i in range(3):
        u = await create_user(db_session, username=f"ubp-pro{i}@axiorapulse.com")
        await create_subscription(db_session, user_id=u.id, plan_id=pro.id, status_name="active")
    for i in range(2):
        u = await create_user(db_session, username=f"ubp-ent{i}@axiorapulse.com")
        await create_subscription(db_session, user_id=u.id, plan_id=ent.id, status_name="active")
    # free users (no entitled subscription)
    await create_user(db_session, username="ubp-free1@axiorapulse.com")
    await create_user(db_session, username="ubp-free2@axiorapulse.com")

    authenticate_as(admin)
    response = await client.get("/api/v1/admin/analytics/users-by-plan")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total_users"] == 7
    by_plan = {p["plan"]: p for p in data["plans"]}
    assert by_plan["pro"]["user_count"] == 3
    assert by_plan["enterprise"]["user_count"] == 2
    assert by_plan["free"]["user_count"] == 2
    assert by_plan["pro"]["percentage"] == pytest.approx(42.9, abs=0.1)


# ── analytics/revenue ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_revenue_requires_admin(client: AsyncClient, db_session: AsyncSession):
    user = await create_user(db_session, username="rev-nonadmin@axiorapulse.com")
    authenticate_as(user)
    response = await client.get("/api/v1/admin/analytics/revenue")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_revenue_today_hourly_includes_only_successful(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_user(db_session, username="rev-admin@axiorapulse.com", role="admin")
    now = datetime.utcnow()
    recent = now - timedelta(hours=1)
    later = now - timedelta(hours=2)

    await create_payment(db_session, user_id=1, amount_paise=50000, status_name="captured", created_at=later)
    await create_payment(db_session, user_id=1, amount_paise=25000, status_name="captured", created_at=recent)
    await create_payment(db_session, user_id=1, amount_paise=99999, status_name="failed", created_at=now)

    authenticate_as(admin)
    response = await client.get("/api/v1/admin/analytics/revenue", params={"period": "today"})
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["period"] == "today"
    # Only the two captured payments count; the failed one is excluded.
    assert data["total_amount"] == 750.0  # INR
    assert len(data["series"]) >= 1
    # Buckets are hourly within the current day.
    assert all(p["period"].endswith(":00") for p in data["series"])
    assert sum(p["amount"] for p in data["series"]) == 750.0


@pytest.mark.asyncio
async def test_revenue_rejects_invalid_period(client: AsyncClient, db_session: AsyncSession):
    admin = await create_user(db_session, username="rev-invalid@axiorapulse.com", role="admin")
    authenticate_as(admin)
    response = await client.get("/api/v1/admin/analytics/revenue", params={"period": "day"})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
