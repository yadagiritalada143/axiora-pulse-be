import base64
import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from types import SimpleNamespace

from sqlalchemy import select
from app.core.dependencies import get_current_user
from app.core.security import hash_password_async
from app.db.models import Role, User, Workspace
from app.models.workspace_models import AttachmentInput
from app.services.attachment_processor import attachment_processor
from app.services.s3_storage_service import s3_storage_service


async def create_test_user(db_session: AsyncSession, username: str, role: str = "member") -> User:
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
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def create_workspace(db_session: AsyncSession, user_id: int, name: str) -> Workspace:
    workspace = Workspace(
        user_id=user_id,
        name=name,
        description="Attachment test workspace",
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
    role_name = user._primary_role

    def _has_role(name: str) -> bool:
        return role_name == name

    current_user = SimpleNamespace(id=user.id, username=user.username, role=role_name, has_role=_has_role)

    async def _mock_current_user():
        return current_user

    from main import app
    app.dependency_overrides[get_current_user] = _mock_current_user


@pytest.mark.asyncio
async def test_s3_storage_service_fallback():
    file_bytes = b"Hello Axiora S3 Storage Test"
    file_url, storage_path = s3_storage_service.upload_file_bytes(
        file_bytes=file_bytes,
        filename="test_file.txt",
        workspace_id=999,
        content_type="text/plain"
    )
    assert file_url is not None
    assert "test_file.txt" in file_url or "999" in file_url
    assert storage_path is not None


@pytest.mark.asyncio
async def test_attachment_processor_doc_and_link():
    doc_text = "This is a startup business plan description for testing."
    encoded_doc = base64.b64encode(doc_text.encode("utf-8")).decode("utf-8")

    attachments = [
        AttachmentInput(
            type="doc",
            name="plan.txt",
            url_or_data=encoded_doc,
            mime_type="text/plain",
        ),
        AttachmentInput(
            type="link",
            name="Sample Website",
            url_or_data="https://example.com",
        )
    ]

    items, text_context, image_uris = await attachment_processor.process_attachments(attachments, workspace_id=123)

    assert len(items) == 2
    assert items[0].type == "doc"
    assert items[0].name == "plan.txt"
    assert "business plan description" in text_context
    assert items[1].type == "link"


@pytest.mark.asyncio
async def test_attachment_processor_jpeg_image():
    dummy_jpeg_base64 = "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP...="
    attachments = [
        AttachmentInput(
            type="image",
            name="diagram.jpeg",
            url_or_data=dummy_jpeg_base64,
            mime_type="image/jpeg",
        )
    ]
    items, text_context, image_uris = await attachment_processor.process_attachments(attachments, workspace_id=456)
    assert len(items) == 1
    assert items[0].type == "image"
    assert items[0].name == "diagram.jpeg"
    assert len(image_uris) == 1
    assert image_uris[0].startswith("data:image/jpeg;base64,")


@pytest.mark.asyncio
async def test_workspace_chat_api_with_attachments(client: AsyncClient, db_session: AsyncSession):
    user = await create_test_user(db_session, username="attachment_user@axiora.com")
    workspace = await create_workspace(db_session, user_id=user.id, name="Multimodal Workspace")
    authenticate_as(user)

    doc_text = "Problem Statement: Small businesses struggle with automated invoice processing."
    encoded_doc = base64.b64encode(doc_text.encode("utf-8")).decode("utf-8")

    payload = {
        "message": "I uploaded my pitch deck draft. Please review it.",
        "attachments": [
            {
                "type": "doc",
                "name": "pitch_deck.txt",
                "url_or_data": encoded_doc,
                "mime_type": "text/plain"
            }
        ]
    }

    response = await client.post(f"/api/v1/workspaces/{workspace.id}/chat", json=payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert "reply" in data
    assert data["workspace_id"] == workspace.id

    from sqlalchemy import select
    from app.db.models import WorkspaceAttachment
    result = await db_session.execute(
        select(WorkspaceAttachment).where(WorkspaceAttachment.workspace_id == workspace.id)
    )
    records = result.scalars().all()
    assert len(records) == 1
    assert records[0].file_name == "pitch_deck.txt"
    assert records[0].file_type == "doc"


@pytest.mark.asyncio
async def test_shared_file_with_arya_not_duplicated_in_attachments_folder(
    client: AsyncClient, db_session: AsyncSession
):
    """
    Verifies that uploading a file and then sharing it with Arya in chat
    results in only a single entry in the Attachments folder / list.
    """
    user = await create_test_user(db_session, username="arya_dedup@axiora.com")
    workspace = await create_workspace(db_session, user_id=user.id, name="Arya Dedup WS")
    authenticate_as(user)

    file_bytes = b"%PDF-1.4 sample pdf content for startup deck"
    # Step 1: User uploads file to workspace
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace.id}/attachments",
        files={"file": ("startup_deck.pdf", file_bytes, "application/pdf")},
    )
    assert upload_resp.status_code == status.HTTP_201_CREATED
    uploaded_data = upload_resp.json()
    file_url = uploaded_data["file_url"]

    # Step 2: User shares the uploaded file with Arya in chat
    chat_payload = {
        "message": "Arya, please review my pitch deck!",
        "attachments": [
            {
                "type": "pdf",
                "name": "startup_deck.pdf",
                "url_or_data": file_url,
                "mime_type": "application/pdf",
            }
        ],
    }
    chat_resp = await client.post(f"/api/v1/workspaces/{workspace.id}/chat", json=chat_payload)
    assert chat_resp.status_code == status.HTTP_200_OK

    # Step 3: User sends a second chat message with the same attachment
    chat_payload2 = {
        "message": "Arya, what do you think about slide 2 of startup_deck.pdf?",
        "attachments": [
            {
                "type": "pdf",
                "name": "startup_deck.pdf",
                "url_or_data": file_url,
                "mime_type": "application/pdf",
            }
        ],
    }
    chat_resp2 = await client.post(f"/api/v1/workspaces/{workspace.id}/chat", json=chat_payload2)
    assert chat_resp2.status_code == status.HTTP_200_OK

    # Step 4: Verify that GET /attachments returns only a SINGLE entry
    list_resp = await client.get(f"/api/v1/workspaces/{workspace.id}/attachments")
    assert list_resp.status_code == status.HTTP_200_OK
    list_data = list_resp.json()
    assert list_data["total"] == 1
    assert len(list_data["attachments"]) == 1
    assert list_data["attachments"][0]["file_name"] == "startup_deck.pdf"


@pytest.mark.asyncio
async def test_reuploading_same_file_updates_existing_attachment(
    client: AsyncClient, db_session: AsyncSession
):
    """
    Verifies that re-uploading a file with the same name replaces/updates
    the existing record instead of adding a duplicate.
    """
    user = await create_user_helper(db_session, "reupload_user@axiora.com")
    workspace = await create_workspace(db_session, user_id=user.id, name="Reupload WS")
    authenticate_as(user)

    file_bytes_v1 = b"%PDF-1.4 version 1 content"
    file_bytes_v2 = b"%PDF-1.4 version 2 updated content"

    resp1 = await client.post(
        f"/api/v1/workspaces/{workspace.id}/attachments",
        files={"file": ("report.pdf", file_bytes_v1, "application/pdf")},
    )
    assert resp1.status_code == status.HTTP_201_CREATED
    att_id_v1 = resp1.json()["id"]

    resp2 = await client.post(
        f"/api/v1/workspaces/{workspace.id}/attachments",
        files={"file": ("report.pdf", file_bytes_v2, "application/pdf")},
    )
    assert resp2.status_code == status.HTTP_201_CREATED
    att_id_v2 = resp2.json()["id"]

    assert att_id_v1 == att_id_v2

    list_resp = await client.get(f"/api/v1/workspaces/{workspace.id}/attachments")
    assert list_resp.status_code == status.HTTP_200_OK
    data = list_resp.json()
    assert data["total"] == 1
    assert len(data["attachments"]) == 1


async def create_user_helper(db_session: AsyncSession, username: str) -> User:
    return await create_test_user(db_session, username)


