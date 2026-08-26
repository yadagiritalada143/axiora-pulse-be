import base64
import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from types import SimpleNamespace

from app.core.dependencies import get_current_user
from app.core.security import hash_password_async
from app.db.models import User, Workspace
from app.models.workspace_models import AttachmentInput
from app.services.attachment_processor import attachment_processor
from app.services.s3_storage_service import s3_storage_service


async def create_test_user(db_session: AsyncSession, username: str) -> User:
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
    current_user = SimpleNamespace(id=user.id, username=user.username, role=user.role)

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

