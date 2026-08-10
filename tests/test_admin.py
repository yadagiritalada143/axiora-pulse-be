import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from types import SimpleNamespace

from app.core.dependencies import get_current_user
from app.core.security import hash_password_async
from app.db.models import User, Workspace


# helpers

async def create_test_user(
    db_session: AsyncSession,
    *,
    username: str,
    role: str = "user",
    display_name: str | None = None,
) -> User:
    user = User(
        username=username,
        password=await hash_password_async("Test@12345"),
        role=role,
        display_name=display_name,
        register_mfa=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def create_workspace(db_session: AsyncSession, *, user_id: int, name: str) -> Workspace:
    workspace = Workspace(
        user_id=user_id,
        name=name,
        description=None,
        state="GATHERING_INFO",
        idea={},
        conversation_history=[],
        validation_result=None,
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)
    return workspace


def authenticate_as(user: User) -> None:
    current_user = SimpleNamespace(id=user.id, username=user.username, role=user.role)

    async def _mock_current_user():
        return current_user

    from main import app

    app.dependency_overrides[get_current_user] = _mock_current_user


# get /api/v1/admin/users

@pytest.mark.asyncio
async def test_list_users_requires_admin(client: AsyncClient, db_session: AsyncSession):
    user = await create_test_user(db_session, username="admin-list-nonadmin@axiorapulse.com")
    authenticate_as(user)

    response = await client.get("/api/v1/admin/users")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_list_users_rejects_unauthenticated_requests(client: AsyncClient):
    response = await client.get("/api/v1/admin/users")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_list_users_returns_paginated_directory_with_workspace_counts(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_test_user(db_session, username="admin-list-admin@axiorapulse.com", role="admin")
    user_a = await create_test_user(db_session, username="admin-list-a@axiorapulse.com")
    user_b = await create_test_user(db_session, username="admin-list-b@axiorapulse.com")
    await create_workspace(db_session, user_id=user_a.id, name="WS 1")
    await create_workspace(db_session, user_id=user_a.id, name="WS 2")
    authenticate_as(admin)

    response = await client.get("/api/v1/admin/users")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    users_by_id = {u["id"]: u for u in data["users"]}
    assert users_by_id[user_a.id]["workspace_count"] == 2
    assert users_by_id[user_b.id]["workspace_count"] == 0
    assert data["pagination"]["total"] == len(data["users"])


@pytest.mark.asyncio
async def test_list_users_pagination_limit_and_offset(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_test_user(db_session, username="admin-list-page-admin@axiorapulse.com", role="admin")
    for i in range(5):
        await create_test_user(db_session, username=f"admin-list-page-{i}@axiorapulse.com")
    authenticate_as(admin)

    response = await client.get("/api/v1/admin/users", params={"limit": 2, "offset": 0})

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["users"]) == 2
    assert data["pagination"]["limit"] == 2
    assert data["pagination"]["offset"] == 0
    assert data["pagination"]["total"] == 6  # 5 seeded + the admin itself


@pytest.mark.asyncio
async def test_list_users_search_filters_by_username_and_display_name(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_test_user(db_session, username="admin-search-admin@axiorapulse.com", role="admin")
    await create_test_user(
        db_session, username="findme@axiorapulse.com", display_name="Findable Person"
    )
    await create_test_user(db_session, username="nomatch@axiorapulse.com", display_name="Someone Else")
    authenticate_as(admin)

    response = await client.get("/api/v1/admin/users", params={"search": "findme"})

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["users"]) == 1
    assert data["users"][0]["username"] == "findme@axiorapulse.com"


@pytest.mark.asyncio
async def test_list_users_search_by_display_name(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_test_user(db_session, username="admin-search-name-admin@axiorapulse.com", role="admin")
    await create_test_user(
        db_session, username="displayname-match@axiorapulse.com", display_name="Unique Display Name"
    )
    authenticate_as(admin)

    response = await client.get("/api/v1/admin/users", params={"search": "Unique Display"})

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["users"]) == 1
    assert data["users"][0]["display_name"] == "Unique Display Name"


@pytest.mark.asyncio
async def test_list_users_rejects_invalid_pagination_params(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_test_user(db_session, username="admin-invalid-params@axiorapulse.com", role="admin")
    authenticate_as(admin)

    response = await client.get("/api/v1/admin/users", params={"limit": 0})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    response_over = await client.get("/api/v1/admin/users", params={"limit": 101})
    assert response_over.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    response_negative_offset = await client.get("/api/v1/admin/users", params={"offset": -1})
    assert response_negative_offset.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
