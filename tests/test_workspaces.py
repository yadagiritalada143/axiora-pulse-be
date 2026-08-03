import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from types import SimpleNamespace

from app.core.dependencies import get_current_user
from app.core.security import hash_password_async
from app.db.models import User, Workspace


async def create_test_user(
    db_session: AsyncSession,
    *,
    username: str,
) -> User:
    user = User(
        username=username,
        password=await hash_password_async("Test@12345"),
        role="user",
        register_mfa=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def create_workspace(
    db_session: AsyncSession,
    *,
    user_id: int,
    name: str,
    description: str | None = None,
) -> Workspace:
    workspace = Workspace(
        user_id=user_id,
        name=name,
        description=description,
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


@pytest.mark.asyncio
async def test_list_workspaces_returns_only_authenticated_users_workspaces(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user_a = await create_test_user(db_session, username="workspace-a@axiorapulse.com")
    user_b = await create_test_user(db_session, username="workspace-b@axiorapulse.com")
    workspace_a = await create_workspace(db_session, user_id=user_a.id, name="User A Workspace")
    await create_workspace(db_session, user_id=user_b.id, name="User B Workspace")
    authenticate_as(user_a)

    response = await client.get("/api/v1/workspaces")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total"] == 1
    assert data["workspaces"][0]["id"] == workspace_a.id
    assert data["workspaces"][0]["user_id"] == user_a.id
    assert data["workspaces"][0]["name"] == "User A Workspace"


@pytest.mark.asyncio
async def test_list_workspaces_rejects_unauthenticated_requests(client: AsyncClient):
    response = await client.get("/api/v1/workspaces")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_create_workspace_with_name_and_description_returns_generated_id(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await create_test_user(db_session, username="workspace-create@axiorapulse.com")
    authenticate_as(user)

    response = await client.post(
        "/api/v1/workspaces",
        json={"name": "Launch Plan", "description": "First validation workspace"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert isinstance(data["id"], int)
    assert data["id"] > 0
    assert data["user_id"] == user.id
    assert data["name"] == "Launch Plan"
    assert data["description"] == "First validation workspace"

    saved = await db_session.get(Workspace, data["id"])
    assert saved is not None
    assert saved.user_id == user.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"name": "No Description"},
        {"name": "Null Description", "description": None},
    ],
)
async def test_create_workspace_allows_missing_or_null_description(
    client: AsyncClient,
    db_session: AsyncSession,
    payload: dict,
):
    username = payload["name"].lower().replace(" ", "-")
    user = await create_test_user(db_session, username=f"{username}@axiorapulse.com")
    authenticate_as(user)

    response = await client.post("/api/v1/workspaces", json=payload)

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["description"] is None
    saved = await db_session.get(Workspace, data["id"])
    assert saved is not None
    assert saved.description is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"name": ""},
        {"name": "x" * 101},
        {"description": "missing name"},
    ],
)
async def test_create_workspace_rejects_invalid_payloads(
    client: AsyncClient,
    db_session: AsyncSession,
    payload: dict,
):
    user = await create_test_user(db_session, username="workspace-invalid@axiorapulse.com")
    authenticate_as(user)

    response = await client.post("/api/v1/workspaces", json=payload)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_get_update_delete_workspace_enforce_ownership(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner = await create_test_user(db_session, username="workspace-owner@axiorapulse.com")
    other_user = await create_test_user(db_session, username="workspace-other@axiorapulse.com")
    workspace = await create_workspace(
        db_session,
        user_id=owner.id,
        name="Private Workspace",
        description="Owner only",
    )
    workspace_id = workspace.id
    authenticate_as(other_user)

    get_response = await client.get(f"/api/v1/workspaces/{workspace_id}")
    assert get_response.status_code == status.HTTP_403_FORBIDDEN

    put_response = await client.put(
        f"/api/v1/workspaces/{workspace_id}",
        json={"name": "Hijacked", "description": "Should fail"},
    )
    assert put_response.status_code == status.HTTP_403_FORBIDDEN

    delete_response = await client.delete(f"/api/v1/workspaces/{workspace_id}")
    assert delete_response.status_code == status.HTTP_403_FORBIDDEN

    await db_session.refresh(workspace)
    assert workspace.name == "Private Workspace"
    result = await db_session.execute(select(Workspace).where(Workspace.id == workspace_id))
    assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_workspace_owner_can_get_update_and_delete_workspace(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner = await create_test_user(db_session, username="workspace-owner-ok@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id, name="Original")
    authenticate_as(owner)

    get_response = await client.get(f"/api/v1/workspaces/{workspace.id}")
    assert get_response.status_code == status.HTTP_200_OK
    assert get_response.json()["id"] == workspace.id

    update_response = await client.put(
        f"/api/v1/workspaces/{workspace.id}",
        json={"name": "Updated", "description": None},
    )
    assert update_response.status_code == status.HTTP_200_OK
    assert update_response.json()["name"] == "Updated"
    assert update_response.json()["description"] is None

    delete_response = await client.delete(f"/api/v1/workspaces/{workspace.id}")
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT
    assert await db_session.get(Workspace, workspace.id) is None
