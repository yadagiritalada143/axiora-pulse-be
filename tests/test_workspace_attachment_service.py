"""
tests/test_workspace_attachment_service.py
────────────────────────────────────────────────────────────────────────────────
Covers the WorkspaceAttachmentService class methods (upload_file, save_from_base64,
list_attachments, get_attachment, delete_attachment, ownership checks) — the
module-level validation helpers (_detect_file_type, _validate_uploaded_file) are
already covered by tests/test_workspace_attachments.py.
"""
import base64
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.security import hash_password_async
from app.db.models import User, Workspace
from app.services.workspace_attachment_service import workspace_attachment_service

_UPLOADS_DIR = Path("uploads")
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20


@pytest.fixture(autouse=True)
def _cleanup_uploads_dir():
    before = set(_UPLOADS_DIR.rglob("*")) if _UPLOADS_DIR.exists() else set()
    yield
    if not _UPLOADS_DIR.exists():
        return
    after = set(_UPLOADS_DIR.rglob("*"))
    for entry in sorted(after - before, key=lambda p: len(p.parts), reverse=True):
        if not entry.exists():
            continue
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            entry.unlink(missing_ok=True)


async def create_user(db_session: AsyncSession, username: str) -> User:
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


async def create_workspace(db_session: AsyncSession, user_id: int, name: str) -> Workspace:
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


# ── Upload (HTTP) ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_attachment_success(client: AsyncClient, db_session: AsyncSession):
    user = await create_user(db_session, "attach-upload@axiorapulse.com")
    workspace = await create_workspace(db_session, user.id, "Upload WS")
    authenticate_as(user)

    response = await client.post(
        f"/api/v1/workspaces/{workspace.id}/attachments",
        files={"file": ("logo.png", _PNG_BYTES, "image/png")},
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["file_name"] == "logo.png"
    assert data["file_type"] == "image"
    assert data["file_url"]


@pytest.mark.asyncio
async def test_upload_attachment_to_nonexistent_workspace_returns_404(client: AsyncClient, db_session: AsyncSession):
    user = await create_user(db_session, "attach-upload-404@axiorapulse.com")
    authenticate_as(user)

    response = await client.post(
        "/api/v1/workspaces/999999/attachments",
        files={"file": ("logo.png", _PNG_BYTES, "image/png")},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_upload_attachment_to_foreign_workspace_returns_403(client: AsyncClient, db_session: AsyncSession):
    owner = await create_user(db_session, "attach-owner@axiorapulse.com")
    intruder = await create_user(db_session, "attach-intruder@axiorapulse.com")
    workspace = await create_workspace(db_session, owner.id, "Owner WS")
    authenticate_as(intruder)

    response = await client.post(
        f"/api/v1/workspaces/{workspace.id}/attachments",
        files={"file": ("logo.png", _PNG_BYTES, "image/png")},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_upload_attachment_invalid_file_returns_400(client: AsyncClient, db_session: AsyncSession):
    user = await create_user(db_session, "attach-invalid@axiorapulse.com")
    workspace = await create_workspace(db_session, user.id, "Invalid WS")
    authenticate_as(user)

    response = await client.post(
        f"/api/v1/workspaces/{workspace.id}/attachments",
        files={"file": ("malware.exe", b"MZ\x90\x00", "application/x-msdownload")},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ── List ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_attachments_empty(client: AsyncClient, db_session: AsyncSession):
    user = await create_user(db_session, "attach-list-empty@axiorapulse.com")
    workspace = await create_workspace(db_session, user.id, "Empty WS")
    authenticate_as(user)

    response = await client.get(f"/api/v1/workspaces/{workspace.id}/attachments")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["total"] == 0


@pytest.mark.asyncio
async def test_list_attachments_returns_uploaded_items_and_supports_file_type_filter(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_user(db_session, "attach-list@axiorapulse.com")
    workspace = await create_workspace(db_session, user.id, "List WS")
    authenticate_as(user)

    await client.post(
        f"/api/v1/workspaces/{workspace.id}/attachments",
        files={"file": ("logo.png", _PNG_BYTES, "image/png")},
    )
    await client.post(
        f"/api/v1/workspaces/{workspace.id}/attachments",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )

    all_resp = await client.get(f"/api/v1/workspaces/{workspace.id}/attachments")
    assert all_resp.json()["total"] == 2

    filtered_resp = await client.get(f"/api/v1/workspaces/{workspace.id}/attachments?file_type=image")
    filtered = filtered_resp.json()
    assert filtered["total"] == 1
    assert filtered["attachments"][0]["file_type"] == "image"


@pytest.mark.asyncio
async def test_list_attachments_for_foreign_workspace_returns_403(client: AsyncClient, db_session: AsyncSession):
    owner = await create_user(db_session, "attach-list-owner@axiorapulse.com")
    intruder = await create_user(db_session, "attach-list-intruder@axiorapulse.com")
    workspace = await create_workspace(db_session, owner.id, "Owner List WS")
    authenticate_as(intruder)

    response = await client.get(f"/api/v1/workspaces/{workspace.id}/attachments")
    assert response.status_code == status.HTTP_403_FORBIDDEN


# ── Get single ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_attachment_success(client: AsyncClient, db_session: AsyncSession):
    user = await create_user(db_session, "attach-get@axiorapulse.com")
    workspace = await create_workspace(db_session, user.id, "Get WS")
    authenticate_as(user)

    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace.id}/attachments",
        files={"file": ("logo.png", _PNG_BYTES, "image/png")},
    )
    attachment_id = upload_resp.json()["id"]

    response = await client.get(f"/api/v1/workspaces/{workspace.id}/attachments/{attachment_id}")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == attachment_id


@pytest.mark.asyncio
async def test_get_attachment_not_found_returns_404(client: AsyncClient, db_session: AsyncSession):
    user = await create_user(db_session, "attach-get-404@axiorapulse.com")
    workspace = await create_workspace(db_session, user.id, "Get 404 WS")
    authenticate_as(user)

    response = await client.get(f"/api/v1/workspaces/{workspace.id}/attachments/999999")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_get_attachment_owned_by_another_user_returns_403(client: AsyncClient, db_session: AsyncSession):
    owner = await create_user(db_session, "attach-get-owner@axiorapulse.com")
    intruder = await create_user(db_session, "attach-get-intruder@axiorapulse.com")
    workspace = await create_workspace(db_session, owner.id, "Get Owner WS")
    authenticate_as(owner)
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace.id}/attachments",
        files={"file": ("logo.png", _PNG_BYTES, "image/png")},
    )
    attachment_id = upload_resp.json()["id"]

    authenticate_as(intruder)
    response = await client.get(f"/api/v1/workspaces/{workspace.id}/attachments/{attachment_id}")
    assert response.status_code == status.HTTP_403_FORBIDDEN


# ── Delete ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_attachment_success(client: AsyncClient, db_session: AsyncSession):
    user = await create_user(db_session, "attach-delete@axiorapulse.com")
    workspace = await create_workspace(db_session, user.id, "Delete WS")
    authenticate_as(user)

    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace.id}/attachments",
        files={"file": ("logo.png", _PNG_BYTES, "image/png")},
    )
    attachment_id = upload_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/workspaces/{workspace.id}/attachments/{attachment_id}")
    assert delete_resp.status_code == status.HTTP_200_OK
    assert delete_resp.json()["attachment_id"] == attachment_id

    get_resp = await client.get(f"/api/v1/workspaces/{workspace.id}/attachments/{attachment_id}")
    assert get_resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_delete_attachment_not_found_returns_404(client: AsyncClient, db_session: AsyncSession):
    user = await create_user(db_session, "attach-delete-404@axiorapulse.com")
    workspace = await create_workspace(db_session, user.id, "Delete 404 WS")
    authenticate_as(user)

    response = await client.delete(f"/api/v1/workspaces/{workspace.id}/attachments/999999")
    assert response.status_code == status.HTTP_404_NOT_FOUND


# ── save_from_base64 (direct unit test — used by chat attachment sync) ────────

@pytest.mark.asyncio
async def test_save_from_base64_success(db_session: AsyncSession):
    user = await create_user(db_session, "attach-b64@axiorapulse.com")
    workspace = await create_workspace(db_session, user.id, "B64 WS")

    encoded = base64.b64encode(_PNG_BYTES).decode()
    result = await workspace_attachment_service.save_from_base64(
        workspace_id=workspace.id,
        user_id=user.id,
        filename="chat-image.png",
        base64_data=encoded,
        mime_type="image/png",
        db=db_session,
    )

    assert result is not None
    assert result.file_name == "chat-image.png"
    assert result.file_type == "image"


@pytest.mark.asyncio
async def test_save_from_base64_returns_none_on_invalid_data(db_session: AsyncSession):
    user = await create_user(db_session, "attach-b64-fail@axiorapulse.com")
    workspace = await create_workspace(db_session, user.id, "B64 Fail WS")

    result = await workspace_attachment_service.save_from_base64(
        workspace_id=workspace.id,
        user_id=user.id,
        filename="bad.exe",
        base64_data=base64.b64encode(b"not a real image").decode(),
        mime_type="application/x-msdownload",
        db=db_session,
    )

    assert result is None


@pytest.mark.asyncio
async def test_save_from_base64_handles_data_uri_prefix(db_session: AsyncSession):
    user = await create_user(db_session, "attach-b64-prefix@axiorapulse.com")
    workspace = await create_workspace(db_session, user.id, "B64 Prefix WS")

    data_uri = "data:image/png;base64," + base64.b64encode(_PNG_BYTES).decode()
    result = await workspace_attachment_service.save_from_base64(
        workspace_id=workspace.id,
        user_id=user.id,
        filename="prefixed.png",
        base64_data=data_uri,
        mime_type="image/png",
        db=db_session,
    )

    assert result is not None
    assert result.file_name == "prefixed.png"
