import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.security import hash_password_async
from app.db.models import User


# helpers

async def create_test_user(
    db_session: AsyncSession,
    *,
    username: str,
    display_name: str | None = None,
) -> User:
    user = User(
        username=username,
        password=await hash_password_async("Test@12345"),
        role="user",
        display_name=display_name,
        register_mfa=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def authenticate_as(user: User) -> None:
    # The profile-update route calls db.refresh(current_user), which requires a real
    # ORM instance attached to the session — a SimpleNamespace stand-in won't work here.
    async def _mock_current_user():
        return user

    from main import app

    app.dependency_overrides[get_current_user] = _mock_current_user


# get /api/auth/me

@pytest.mark.asyncio
async def test_get_current_user_profile_with_display_name(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(
        db_session, username="profile-me@axiorapulse.com", display_name="Test Person"
    )
    authenticate_as(user)

    response = await client.get("/api/auth/me")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == str(user.id)
    assert data["email"] == user.username
    assert data["name"] == "Test Person"
    assert data["role"] == "user"


@pytest.mark.asyncio
async def test_get_current_user_profile_falls_back_to_username_prefix(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="fallback-name@axiorapulse.com")
    authenticate_as(user)

    response = await client.get("/api/auth/me")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["name"] == "fallback-name"  # username local-part, no display_name set



# patch /api/users/me

@pytest.mark.asyncio
async def test_update_current_user_profile_updates_name_and_email(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="update-me@axiorapulse.com")
    authenticate_as(user)

    response = await client.patch(
        "/api/users/me",
        json={"name": "New Name", "email": "updated-me@axiorapulse.com"},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["data"]
    assert data["name"] == "New Name"
    assert data["email"] == "updated-me@axiorapulse.com"

    await db_session.refresh(user)
    assert user.display_name == "New Name"
    assert user.username == "updated-me@axiorapulse.com"


@pytest.mark.asyncio
async def test_update_current_user_profile_allows_keeping_same_email(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="same-email@axiorapulse.com")
    authenticate_as(user)

    response = await client.patch(
        "/api/users/me",
        json={"name": "Renamed Only", "email": "same-email@axiorapulse.com"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"]["name"] == "Renamed Only"


@pytest.mark.asyncio
async def test_update_current_user_profile_rejects_email_already_in_use(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="taken-checker@axiorapulse.com")
    await create_test_user(db_session, username="already-taken@axiorapulse.com")
    authenticate_as(user)

    response = await client.patch(
        "/api/users/me",
        json={"name": "Someone", "email": "already-taken@axiorapulse.com"},
    )

    assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_update_current_user_profile_rejects_invalid_payload(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="invalid-payload@axiorapulse.com")
    authenticate_as(user)

    response = await client.patch(
        "/api/users/me",
        json={"name": "", "email": "not-an-email"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


