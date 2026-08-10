"""
backend/tests/test_workspace_attachments.py
────────────────────────────────────────────────────────────────────────────────
Unit / integration tests for workspace attachment upload, listing, get, and delete.
"""
import pytest
from fastapi import HTTPException

from app.services.workspace_attachment_service import (
    MAX_FILE_SIZE_BYTES,
    _detect_file_type,
    _validate_uploaded_file,
)
from app.services.s3_storage_service import s3_storage_service


def test_detect_file_type_valid():
    assert _detect_file_type("document.pdf", "application/pdf") == "pdf"
    assert _detect_file_type("image.png", "image/png") == "image"
    assert _detect_file_type("photo.jpg", "image/jpeg") == "image"
    assert _detect_file_type("report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document") == "doc"
    assert _detect_file_type("notes.txt", "text/plain") == "doc"


def test_detect_file_type_rejected():
    # Unknown extensions / binary fallbacks must return None (not 'doc')
    assert _detect_file_type("custom_file.bin", "application/octet-stream") is None
    # SVG must be rejected
    assert _detect_file_type("vector.svg", "image/svg+xml") is None
    # Executable files
    assert _detect_file_type("app.exe", "application/x-msdownload") is None
    # Mismatched content-type and extension
    assert _detect_file_type("photo.png", "application/pdf") is None


def test_validate_uploaded_file_valid_png():
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    assert _validate_uploaded_file(png_bytes, "test.png", "image/png") == "image"


def test_validate_uploaded_file_valid_pdf():
    pdf_bytes = b"%PDF-1.4\n" + b"\x00" * 20
    assert _validate_uploaded_file(pdf_bytes, "document.pdf", "application/pdf") == "pdf"


def test_validate_uploaded_file_valid_docx():
    docx_bytes = b"PK\x03\x04" + b"\x00" * 20
    assert _validate_uploaded_file(docx_bytes, "report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document") == "doc"


def test_validate_uploaded_file_forbidden_extension():
    with pytest.raises(HTTPException) as exc_info:
        _validate_uploaded_file(b"<?php phpinfo(); ?>", "shell.php", "text/plain")
    assert exc_info.value.status_code == 400
    assert "forbidden" in exc_info.value.detail.lower()


def test_validate_uploaded_file_svg_rejection():
    with pytest.raises(HTTPException) as exc_info:
        _validate_uploaded_file(b"<svg><script>alert(1)</script></svg>", "icon.svg", "image/svg+xml")
    assert exc_info.value.status_code == 400


def test_validate_uploaded_file_text_script_rejection():
    with pytest.raises(HTTPException) as exc_info:
        _validate_uploaded_file(b"Hello <script>alert(1)</script>", "notes.txt", "text/plain")
    assert exc_info.value.status_code == 400
    assert "forbidden script" in exc_info.value.detail.lower()


def test_validate_uploaded_file_invalid_image_signature():
    fake_png_bytes = b"NOT_A_PNG_HEADER" + b"\x00" * 20
    with pytest.raises(HTTPException) as exc_info:
        _validate_uploaded_file(fake_png_bytes, "fake.png", "image/png")
    assert exc_info.value.status_code == 400
    assert "image signature" in exc_info.value.detail.lower()


def test_validate_uploaded_file_oversized():
    huge_bytes = b"a" * (MAX_FILE_SIZE_BYTES + 1)
    with pytest.raises(HTTPException) as exc_info:
        _validate_uploaded_file(huge_bytes, "huge.txt", "text/plain")
    assert exc_info.value.status_code == 400
    assert "maximum limit" in exc_info.value.detail.lower()


def test_s3_storage_service_generate_presigned_url():
    url = s3_storage_service.generate_presigned_url("Assets/test/key.pdf")
    assert url is not None
    assert "key.pdf" in url or "uploads" in url

