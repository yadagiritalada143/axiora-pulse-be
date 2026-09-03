import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth_service import seed_admin_user


@pytest.mark.asyncio
async def test_full_admin_login_then_authenticated_call(
    client: AsyncClient, db_session: AsyncSession
):
    await seed_admin_user(db_session)

    r = await client.post(
        "/api/v1/auth/admin/login",
        json={"username": "admin@axiorapulse.com", "password": "Test@12345"},
    )
    print("LOGIN status:", r.status_code, "body:", r.text)
    body = r.json()
    token = body["access_token"]
    role = body["role"]

    r2 = await client.get(
        "/api/v1/admin/dashboard/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    print("DASHBOARD status:", r2.status_code, "body:", r2.text)
    print("LOGIN role:", role)

    assert r.status_code == 200
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_full_user_login_otp_flow(client: AsyncClient, db_session: AsyncSession):
    import os
    from app.core.security import hash_password_async
    from app.db.models import Role, User
    from sqlalchemy import select

    role = (await db_session.execute(select(Role).where(Role.name == "viewer"))).scalar_one_or_none()
    if role is None:
        role = Role(name="viewer", description="starter")
        db_session.add(role)
        await db_session.flush()
    u = User(
        username="user-repro@axiorapulse.com",
        password=await hash_password_async("Test@12345"),
        register_mfa=True,
        role=role,
    )
    db_session.add(u)
    await db_session.commit()

    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "user-repro@axiorapulse.com", "password": "Test@12345"},
    )
    print("USER LOGIN status:", r.status_code, "body:", r.text)
    await db_session.refresh(u)
    print("login_otp =", u.login_otp)
    otp = u.login_otp

    r2 = await client.post(
        "/api/v1/auth/verify-login",
        json={"emailOrMobile": "user-repro@axiorapulse.com", "otp": otp},
    )
    print("VERIFY LOGIN status:", r2.status_code, "body:", r2.text)
    token = r2.json().get("access_token")

    r3 = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    print("ME status:", r3.status_code, "body:", r3.text)

    assert r.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 200
