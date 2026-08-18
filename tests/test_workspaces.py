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
    assert delete_response.status_code == status.HTTP_200_OK
    assert delete_response.json()["workspace_id"] == workspace.id

    await db_session.refresh(workspace)
    assert workspace.is_delete is True  # archived, not hard-deleted


# ──────────────────────────────────────────────────────────────────────────────
# Archive (soft-delete) & Restore
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_archive_and_restore_workspace_flow(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner = await create_test_user(db_session, username="workspace-archive-flow@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id, name="Archivable")
    workspace_id = workspace.id
    authenticate_as(owner)

    # Active by default → visible in the active list, not the archived list
    active_list = await client.get("/api/v1/workspaces", params={"is_delete": False})
    assert workspace_id in [w["id"] for w in active_list.json()["workspaces"]]

    # Archive it
    archive_response = await client.delete(f"/api/v1/workspaces/{workspace_id}")
    assert archive_response.status_code == status.HTTP_200_OK
    body = archive_response.json()
    assert body["workspace_id"] == workspace_id

    # No longer visible in active list, but appears in archived list
    active_list_after = await client.get("/api/v1/workspaces", params={"is_delete": False})
    assert workspace_id not in [w["id"] for w in active_list_after.json()["workspaces"]]
    archived_list = await client.get("/api/v1/workspaces", params={"is_delete": True})
    assert workspace_id in [w["id"] for w in archived_list.json()["workspaces"]]

    # Archived workspace is treated as not-found for direct GET
    get_archived = await client.get(f"/api/v1/workspaces/{workspace_id}")
    assert get_archived.status_code == status.HTTP_404_NOT_FOUND

    # Restore it
    restore_response = await client.patch(f"/api/v1/workspaces/{workspace_id}/restore")
    assert restore_response.status_code == status.HTTP_200_OK
    restore_body = restore_response.json()
    assert restore_body["workspace_id"] == workspace_id
    assert restore_body["is_delete"] is False

    # Visible again in the active list and via direct GET
    active_list_restored = await client.get("/api/v1/workspaces", params={"is_delete": False})
    assert workspace_id in [w["id"] for w in active_list_restored.json()["workspaces"]]
    get_restored = await client.get(f"/api/v1/workspaces/{workspace_id}")
    assert get_restored.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_archive_already_archived_workspace_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner = await create_test_user(db_session, username="workspace-double-archive@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id, name="Double Archive")
    authenticate_as(owner)

    first = await client.delete(f"/api/v1/workspaces/{workspace.id}")
    assert first.status_code == status.HTTP_200_OK

    second = await client.delete(f"/api/v1/workspaces/{workspace.id}")
    assert second.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_restore_non_archived_workspace_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner = await create_test_user(db_session, username="workspace-restore-active@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id, name="Restore Active")
    authenticate_as(owner)

    response = await client.patch(f"/api/v1/workspaces/{workspace.id}/restore")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_archive_and_restore_enforce_ownership(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner = await create_test_user(db_session, username="workspace-archive-owner@axiorapulse.com")
    intruder = await create_test_user(db_session, username="workspace-archive-intruder@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id, name="Owned Workspace")
    workspace_id = workspace.id
    authenticate_as(intruder)

    archive_response = await client.delete(f"/api/v1/workspaces/{workspace_id}")
    assert archive_response.status_code == status.HTTP_403_FORBIDDEN

    restore_response = await client.patch(f"/api/v1/workspaces/{workspace_id}/restore")
    assert restore_response.status_code == status.HTTP_403_FORBIDDEN

    result = await db_session.execute(select(Workspace).where(Workspace.id == workspace_id))
    assert result.scalar_one().is_delete is False


@pytest.mark.asyncio
async def test_archive_nonexistent_workspace_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner = await create_test_user(db_session, username="workspace-archive-404@axiorapulse.com")
    authenticate_as(owner)

    response = await client.delete("/api/v1/workspaces/999999")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_restore_nonexistent_workspace_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner = await create_test_user(db_session, username="workspace-restore-404@axiorapulse.com")
    authenticate_as(owner)

    response = await client.patch("/api/v1/workspaces/999999/restore")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_list_workspaces_defaults_to_active_only(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner = await create_test_user(db_session, username="workspace-list-default@axiorapulse.com")
    active_ws = await create_workspace(db_session, user_id=owner.id, name="Active")
    archived_ws = await create_workspace(db_session, user_id=owner.id, name="ArchivedSeed")
    archived_ws.is_delete = True
    await db_session.commit()
    authenticate_as(owner)

    response = await client.get("/api/v1/workspaces")

    assert response.status_code == status.HTTP_200_OK
    ids = [w["id"] for w in response.json()["workspaces"]]
    assert active_ws.id in ids
    assert archived_ws.id not in ids
