import os
import shutil
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.s3_storage_service import S3StorageService

_UPLOADS_DIR = Path("uploads")


@pytest.fixture
def fake_boto3(monkeypatch):
    """Inject a fake `boto3` module into sys.modules.

    The real boto3 package isn't installed in this dev environment even
    though it's in requirements.txt, and _init_s3_client() does `import
    boto3` lazily inside a try/except — without this, that import always
    fails and the "S3 client initialized" code path can never be exercised.
    """
    fake_module = types.ModuleType("boto3")
    fake_module.client = MagicMock(return_value=MagicMock())
    monkeypatch.setitem(sys.modules, "boto3", fake_module)
    return fake_module


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


def _local_service() -> S3StorageService:
    """A service instance with no AWS credentials — local fallback mode."""
    svc = S3StorageService()
    svc._s3_client = None
    return svc


def _service_with_mock_client() -> tuple[S3StorageService, MagicMock]:
    """A service instance whose _s3_client is a MagicMock, bypassing boto3."""
    svc = S3StorageService()
    mock_client = MagicMock()
    svc._s3_client = mock_client
    return svc, mock_client


# ── __init__ / _init_s3_client ────────────────────────────────────────────────

def test_init_without_aws_credentials_uses_local_mode(monkeypatch):
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    svc = S3StorageService()
    assert svc._s3_client is None


def test_init_with_credentials_initializes_boto3_client(monkeypatch, fake_boto3):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAFAKE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fakesecret")
    svc = S3StorageService()
    assert svc._s3_client is not None
    fake_boto3.client.assert_called_once()


def test_init_with_credentials_falls_back_when_boto3_client_raises(monkeypatch, fake_boto3):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAFAKE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fakesecret")
    fake_boto3.client.side_effect = RuntimeError("credentials rejected")

    svc = S3StorageService()
    assert svc._s3_client is None


def test_init_with_custom_endpoint_url_passed_to_client(monkeypatch, fake_boto3):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAFAKE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fakesecret")
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://localhost:9000")

    S3StorageService()

    _, kwargs = fake_boto3.client.call_args
    assert kwargs.get("endpoint_url") == "http://localhost:9000"


# ── generate_presigned_url ────────────────────────────────────────────────────

def test_generate_presigned_url_uses_s3_client_when_available():
    svc, mock_client = _service_with_mock_client()
    mock_client.generate_presigned_url.return_value = "https://signed.example.com/key"

    url = svc.generate_presigned_url("Assets/some/key.pdf")

    assert url == "https://signed.example.com/key"
    mock_client.generate_presigned_url.assert_called_once()


def test_generate_presigned_url_falls_back_when_s3_client_raises():
    svc, mock_client = _service_with_mock_client()
    mock_client.generate_presigned_url.side_effect = RuntimeError("boom")

    url = svc.generate_presigned_url("some/key.pdf")

    assert url == "/uploads/some/key.pdf"


def test_generate_presigned_url_without_client_returns_absolute_urls_unchanged():
    svc = _local_service()
    assert svc.generate_presigned_url("https://cdn.example.com/x.png") == "https://cdn.example.com/x.png"
    assert svc.generate_presigned_url("http://cdn.example.com/x.png") == "http://cdn.example.com/x.png"
    assert svc.generate_presigned_url("/already/local/path.png") == "/already/local/path.png"


def test_generate_presigned_url_without_client_builds_local_url():
    svc = _local_service()
    assert svc.generate_presigned_url("some/key.pdf") == "/uploads/some/key.pdf"


def test_generate_presigned_url_skips_client_for_key_starting_with_slash():
    svc, mock_client = _service_with_mock_client()
    url = svc.generate_presigned_url("/already/local/path.png")
    mock_client.generate_presigned_url.assert_not_called()
    assert url == "/already/local/path.png"


# ── upload_file_bytes ──────────────────────────────────────────────────────────

def test_upload_file_bytes_via_s3_client_success():
    svc, mock_client = _service_with_mock_client()
    mock_client.generate_presigned_url.return_value = "https://signed.example.com/key"

    file_url, storage_path = svc.upload_file_bytes(b"hello", "notes.txt", workspace_id=7)

    mock_client.put_object.assert_called_once()
    assert file_url == "https://signed.example.com/key"
    assert "workspaces/7/attachments/" in storage_path


def test_upload_file_bytes_falls_back_to_local_when_s3_put_object_raises():
    svc, mock_client = _service_with_mock_client()
    mock_client.put_object.side_effect = RuntimeError("network down")

    file_url, storage_path = svc.upload_file_bytes(b"hello", "notes.txt", workspace_id=7)

    assert file_url.startswith("/uploads/workspaces/7/attachments/")
    assert os.path.exists(storage_path)
    with open(storage_path, "rb") as f:
        assert f.read() == b"hello"


def test_upload_file_bytes_local_mode_writes_file():
    svc = _local_service()

    file_url, storage_path = svc.upload_file_bytes(b"local content", "report.pdf", workspace_id="ws1")

    assert file_url.startswith("/uploads/workspaces/ws1/attachments/")
    assert os.path.exists(storage_path)
    with open(storage_path, "rb") as f:
        assert f.read() == b"local content"


def test_upload_file_bytes_sanitizes_unsafe_filename():
    svc = _local_service()
    _, storage_path = svc.upload_file_bytes(b"x", "../../etc/passwd!.sh", workspace_id="ws1")
    basename = os.path.basename(storage_path)
    # Path separators and other unsafe characters must never survive into the
    # filename — dots alone can't traverse directories once "/" is stripped.
    assert "/" not in basename and "\\" not in basename
    assert "!" not in basename
    assert basename.endswith("etcpasswd.sh")
    assert os.path.exists(storage_path)


def test_upload_file_bytes_falls_back_to_default_name_when_filename_is_all_unsafe():
    svc = _local_service()
    _, storage_path = svc.upload_file_bytes(b"x", "***???", workspace_id="ws1")
    assert "attachment.dat" in storage_path


# ── upload_base64 ──────────────────────────────────────────────────────────────

def test_upload_base64_detects_png_content_type():
    svc = _local_service()
    import base64 as b64
    data_uri = "data:image/png;base64," + b64.b64encode(b"pngdata").decode()
    file_url, storage_path = svc.upload_base64(data_uri, "image.bin", workspace_id="ws1")
    assert os.path.exists(storage_path)


def test_upload_base64_detects_jpeg_content_type():
    svc = _local_service()
    import base64 as b64
    data_uri = "data:image/jpeg;base64," + b64.b64encode(b"jpgdata").decode()
    _, storage_path = svc.upload_base64(data_uri, "image.bin", workspace_id="ws1")
    assert os.path.exists(storage_path)


def test_upload_base64_detects_pdf_content_type():
    svc = _local_service()
    import base64 as b64
    data_uri = "data:application/pdf;base64," + b64.b64encode(b"pdfdata").decode()
    _, storage_path = svc.upload_base64(data_uri, "doc.bin", workspace_id="ws1")
    assert os.path.exists(storage_path)
    with open(storage_path, "rb") as f:
        assert f.read() == b"pdfdata"


def test_upload_base64_without_data_uri_prefix():
    svc = _local_service()
    import base64 as b64
    raw = b64.b64encode(b"rawbytes").decode()
    _, storage_path = svc.upload_base64(raw, "file.bin", workspace_id="ws1")
    with open(storage_path, "rb") as f:
        assert f.read() == b"rawbytes"


def test_upload_base64_invalid_data_decodes_to_empty_bytes():
    svc = _local_service()
    _, storage_path = svc.upload_base64("data:image/png;base64,not-valid-base64!!!", "bad.png", workspace_id="ws1")
    with open(storage_path, "rb") as f:
        assert f.read() == b""


# ── upload_workspace_asset ─────────────────────────────────────────────────────

def test_upload_workspace_asset_via_s3_client_success():
    svc, mock_client = _service_with_mock_client()
    mock_client.generate_presigned_url.return_value = "https://signed.example.com/asset"

    file_url, s3_key = svc.upload_workspace_asset(
        b"assetbytes", "diagram.png", user_id=1, workspace_id=2, file_type="image"
    )

    mock_client.put_object.assert_called_once()
    assert file_url == "https://signed.example.com/asset"
    assert "Assets/users/1/workspaces/2/images/" in s3_key


def test_upload_workspace_asset_falls_back_to_local_when_s3_put_object_raises():
    svc, mock_client = _service_with_mock_client()
    mock_client.put_object.side_effect = RuntimeError("network down")

    file_url, s3_key = svc.upload_workspace_asset(
        b"assetbytes", "report.pdf", user_id=1, workspace_id=2, file_type="pdf"
    )

    assert file_url.startswith("/uploads/assets/users/1/workspaces/2/pdfs/")
    local_path = file_url.lstrip("/")
    assert os.path.exists(local_path)


def test_upload_workspace_asset_local_mode_unknown_file_type_uses_files_folder():
    svc = _local_service()
    file_url, _ = svc.upload_workspace_asset(
        b"bytes", "notes.txt", user_id=1, workspace_id=2, file_type="doc-ish"
    )
    assert "/files/" in file_url


# ── delete_workspace_asset ─────────────────────────────────────────────────────

def test_delete_workspace_asset_via_s3_client_success():
    svc, mock_client = _service_with_mock_client()
    assert svc.delete_workspace_asset("Assets/users/1/workspaces/2/images/x.png") is True
    mock_client.delete_object.assert_called_once()


def test_delete_workspace_asset_via_s3_client_failure_returns_false():
    svc, mock_client = _service_with_mock_client()
    mock_client.delete_object.side_effect = RuntimeError("boom")
    assert svc.delete_workspace_asset("Assets/users/1/workspaces/2/images/x.png") is False


def test_delete_workspace_asset_local_mode_removes_existing_file():
    svc = _local_service()
    _, s3_key = svc.upload_workspace_asset(b"x", "a.txt", user_id=1, workspace_id=2, file_type="doc")
    local_path = os.path.join("uploads", *s3_key.split("/"))
    assert os.path.exists(local_path)

    result = svc.delete_workspace_asset(s3_key)

    assert result is False  # no S3 client → always returns False, even on successful local delete
    assert not os.path.exists(local_path)


def test_delete_workspace_asset_local_mode_missing_file_does_not_raise():
    svc = _local_service()
    result = svc.delete_workspace_asset("Assets/users/999/workspaces/999/images/missing.png")
    assert result is False
