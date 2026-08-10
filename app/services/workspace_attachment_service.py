"""
app/services/workspace_attachment_service.py
────────────────────────────────────────────────────────────────────────────────
Workspace Attachment Service — handles file uploads, listing, retrieval, and
deletion of user-uploaded files scoped to a workspace.

Files are stored in the axiora-assets S3 bucket under:
  Assets/users/{user_id}/workspaces/{workspace_id}/{type_folder}/{uuid}_{filename}

Supported file types:
  - image   → images/  (JPEG, JPG, PNG, WEBP, GIF)
  - pdf     → pdfs/    (application/pdf)
  - doc     → docs/    (DOCX, TXT, MD, and other documents)
"""
import logging
from typing import List, Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, Workspace, WorkspaceAttachment
from app.models.workspace_models import (
    DeleteAttachmentResponse,
    WorkspaceAttachmentListResponse,
    WorkspaceAttachmentResponse,
)
from app.services.s3_storage_service import s3_storage_service

logger = logging.getLogger(__name__)

# ── Size limits & Allowlist mappings ──────────────────────────────────────────
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB maximum upload size

MIME_TO_FILE_TYPE: dict[str, str] = {
    # Images (excluding image/svg+xml to prevent XSS)
    "image/jpeg": "image",
    "image/jpg": "image",
    "image/png": "image",
    "image/webp": "image",
    "image/gif": "image",
    "image/bmp": "image",
    # PDFs
    "application/pdf": "pdf",
    # Documents
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "doc",  # .docx
    "application/msword": "doc",                   # .doc
    "text/plain": "doc",                           # .txt
    "text/markdown": "doc",                        # .md
    "application/rtf": "doc",                      # .rtf
    "text/csv": "doc",                             # .csv
}

EXTENSION_TO_FILE_TYPE: dict[str, str] = {
    ".jpg": "image", ".jpeg": "image", ".png": "image",
    ".webp": "image", ".gif": "image", ".bmp": "image",
    ".pdf": "pdf",
    ".docx": "doc", ".doc": "doc", ".txt": "doc",
    ".md": "doc", ".rtf": "doc", ".csv": "doc",
}


def _detect_file_type(filename: str, content_type: str) -> Optional[str]:
    """
    Determine file_type ('image' | 'pdf' | 'doc') from MIME type and extension.
    Enforces a strict allowlist. Returns None if the file type/extension is unknown or mismatched.
    """
    clean_ct = (content_type or "").split(";")[0].strip().lower()
    mime_type_cat = MIME_TO_FILE_TYPE.get(clean_ct)

    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    ext_type_cat = EXTENSION_TO_FILE_TYPE.get(ext)

    # Reject if both extension and content-type are absent from allowlist
    if not mime_type_cat and not ext_type_cat:
        return None

    # If both exist, ensure they match the same file_type category
    if mime_type_cat and ext_type_cat and mime_type_cat != ext_type_cat:
        return None

    return mime_type_cat or ext_type_cat


def _validate_uploaded_file(file_bytes: bytes, filename: str, content_type: str) -> str:
    """
    Validates file size, MIME type allowlist, extension allowlist, and binary file signatures.
    Raises HTTPException (400) if validation fails.
    Returns the validated file_type ('image' | 'pdf' | 'doc').
    """
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds the maximum limit of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.",
        )

    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    # Disallow dangerous executable/script extensions explicitly
    forbidden_exts = {".html", ".htm", ".svg", ".exe", ".sh", ".php", ".js", ".jar", ".bat", ".cmd", ".vbs", ".py"}
    if ext in forbidden_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' is forbidden.",
        )

    file_type = _detect_file_type(filename, content_type)
    if not file_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported file type or extension for filename '{filename}' (content_type='{content_type}'). "
                "Only images (JPEG, PNG, WEBP, GIF, BMP), PDFs, and documents (DOCX, DOC, TXT, MD, RTF, CSV) are allowed."
            ),
        )

    # ── Binary File Signature Validation ──────────────────────────────────────
    if file_type == "image":
        is_valid_image = (
            file_bytes.startswith(b"\x89PNG\r\n\x1a\n") or
            file_bytes.startswith(b"\xff\xd8\xff") or
            file_bytes.startswith(b"GIF87a") or
            file_bytes.startswith(b"GIF89a") or
            file_bytes.startswith(b"BM") or
            (file_bytes.startswith(b"RIFF") and b"WEBP" in file_bytes[8:12])
        )
        if not is_valid_image:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content does not match a valid image signature.",
            )

    elif file_type == "pdf":
        if not file_bytes.startswith(b"%PDF-") and b"%PDF-" not in file_bytes[:1024]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content does not match a valid PDF signature.",
            )

    elif file_type == "doc":
        if ext == ".docx" and not file_bytes.startswith(b"PK\x03\x04"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content does not match a valid DOCX signature.",
            )
        elif ext == ".doc" and not file_bytes.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content does not match a valid DOC signature.",
            )
        elif ext in (".txt", ".md", ".csv", ".rtf"):
            sample = file_bytes[:4096].lower()
            if any(tag in sample for tag in [b"<script", b"<html", b"<?php", b"<iframe", b"<svg"]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Text file contains forbidden script or HTML tags.",
                )

    return file_type


class WorkspaceAttachmentService:
    """Stateless service — all state lives in the DB session."""

    def _format_attachment_response(
        self, attachment: WorkspaceAttachment
    ) -> WorkspaceAttachmentResponse:
        """Format WorkspaceAttachment into WorkspaceAttachmentResponse with fresh presigned URL."""
        resp = WorkspaceAttachmentResponse.model_validate(attachment)
        if attachment.s3_key:
            resp.file_url = s3_storage_service.generate_presigned_url(attachment.s3_key)
        return resp

    # ── Upload ────────────────────────────────────────────────────────────────

    async def upload_file(
        self,
        workspace_id: int,
        current_user: User,
        file: UploadFile,
        db: AsyncSession,
    ) -> WorkspaceAttachmentResponse:
        """
        Read a multipart uploaded file, validate type/signature/size, push it to S3,
        and persist a WorkspaceAttachment record in the database.
        """
        # Verify workspace ownership
        workspace = await self._fetch_owned_workspace(workspace_id, current_user, db)

        file_bytes = await file.read()
        filename = file.filename or "upload"
        content_type = file.content_type or "application/octet-stream"

        file_type = _validate_uploaded_file(file_bytes, filename, content_type)
        file_size = len(file_bytes)

        # Upload to axiora-assets bucket
        file_url, s3_key = s3_storage_service.upload_workspace_asset(
            file_bytes=file_bytes,
            filename=filename,
            user_id=current_user.id,
            workspace_id=workspace.id,
            file_type=file_type,
            content_type=content_type,
        )

        # Persist record
        attachment = WorkspaceAttachment(
            user_id=current_user.id,
            workspace_id=workspace.id,
            file_name=filename,
            file_type=file_type,
            mime_type=content_type,
            s3_key=s3_key,
            file_url=file_url,
            file_size_bytes=file_size,
        )
        db.add(attachment)
        await db.flush()
        await db.refresh(attachment)

        logger.info(
            "[WorkspaceAttachmentService] Uploaded %s (%s) to workspace %s for user %s → %s",
            filename, file_type, workspace_id, current_user.id, file_url
        )
        return self._format_attachment_response(attachment)

    # ── Save from base64 (used by chat sync) ─────────────────────────────────

    async def save_from_base64(
        self,
        workspace_id: int,
        user_id: int,
        filename: str,
        base64_data: str,
        mime_type: str,
        db: AsyncSession,
    ) -> Optional[WorkspaceAttachmentResponse]:
        """
        Decode a base64 attachment (sent inline in chat) and save it to the
        workspace_attachments table. Used for chat attachment sync.

        Returns None silently on any error so chat is not blocked.
        """
        try:
            import base64 as b64lib

            raw = base64_data.split(",", 1)[-1] if "," in base64_data else base64_data
            file_bytes = b64lib.b64decode(raw)
            file_type = _validate_uploaded_file(file_bytes, filename, mime_type)

            file_url, s3_key = s3_storage_service.upload_workspace_asset(
                file_bytes=file_bytes,
                filename=filename,
                user_id=user_id,
                workspace_id=workspace_id,
                file_type=file_type,
                content_type=mime_type or "application/octet-stream",
            )

            attachment = WorkspaceAttachment(
                user_id=user_id,
                workspace_id=workspace_id,
                file_name=filename,
                file_type=file_type,
                mime_type=mime_type or "application/octet-stream",
                s3_key=s3_key,
                file_url=file_url,
                file_size_bytes=len(file_bytes),
            )
            db.add(attachment)
            await db.flush()
            await db.refresh(attachment)

            logger.info(
                "[WorkspaceAttachmentService] Synced chat attachment %s to workspace %s for user %s",
                filename, workspace_id, user_id
            )
            return self._format_attachment_response(attachment)

        except Exception as e:
            logger.warning(
                "[WorkspaceAttachmentService] Failed to sync chat attachment %s: %s",
                filename, e
            )
            return None

    # ── List ──────────────────────────────────────────────────────────────────

    async def list_attachments(
        self,
        workspace_id: int,
        current_user: User,
        db: AsyncSession,
        file_type: Optional[str] = None,
    ) -> WorkspaceAttachmentListResponse:
        """List all attachments for a workspace (optionally filter by file_type)."""
        await self._fetch_owned_workspace(workspace_id, current_user, db)

        query = (
            select(WorkspaceAttachment)
            .where(
                WorkspaceAttachment.workspace_id == workspace_id,
                WorkspaceAttachment.user_id == current_user.id,
            )
            .order_by(WorkspaceAttachment.created_at.desc())
        )
        if file_type:
            query = query.where(WorkspaceAttachment.file_type == file_type)

        result = await db.execute(query)
        attachments = result.scalars().all()

        return WorkspaceAttachmentListResponse(
            total=len(attachments),
            attachments=[self._format_attachment_response(a) for a in attachments],
        )

    # ── Get Single ────────────────────────────────────────────────────────────

    async def get_attachment(
        self,
        workspace_id: int,
        attachment_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> WorkspaceAttachmentResponse:
        """Fetch a single attachment record."""
        attachment = await self._fetch_owned_attachment(
            workspace_id, attachment_id, current_user, db
        )
        return self._format_attachment_response(attachment)

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete_attachment(
        self,
        workspace_id: int,
        attachment_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> DeleteAttachmentResponse:
        """Delete a workspace attachment from S3 and the database."""
        attachment = await self._fetch_owned_attachment(
            workspace_id, attachment_id, current_user, db
        )

        # Remove from S3 (best-effort — don't block if S3 delete fails)
        s3_storage_service.delete_workspace_asset(attachment.s3_key)

        # Remove DB record
        await db.delete(attachment)
        await db.flush()

        logger.info(
            "[WorkspaceAttachmentService] Deleted attachment %s (workspace %s, user %s)",
            attachment_id, workspace_id, current_user.id
        )
        return DeleteAttachmentResponse(
            attachment_id=attachment_id,
            workspace_id=workspace_id,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _fetch_owned_workspace(
        self,
        workspace_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> Workspace:
        """Fetch and ownership-check a workspace; raises 404/403 as appropriate."""
        result = await db.execute(
            select(Workspace).where(
                Workspace.id == workspace_id,
                Workspace.is_delete == False,  # noqa: E712
            )
        )
        workspace = result.scalar_one_or_none()

        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workspace {workspace_id} not found.",
            )
        if workspace.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this workspace.",
            )
        return workspace

    async def _fetch_owned_attachment(
        self,
        workspace_id: int,
        attachment_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> WorkspaceAttachment:
        """Fetch and ownership-check a single attachment; raises 404/403 as appropriate."""
        result = await db.execute(
            select(WorkspaceAttachment).where(
                WorkspaceAttachment.id == attachment_id,
                WorkspaceAttachment.workspace_id == workspace_id,
            )
        )
        attachment = result.scalar_one_or_none()

        if attachment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Attachment {attachment_id} not found in workspace {workspace_id}.",
            )
        if attachment.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this attachment.",
            )
        return attachment


# ── Singleton ─────────────────────────────────────────────────────────────────
workspace_attachment_service = WorkspaceAttachmentService()
