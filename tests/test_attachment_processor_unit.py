import base64
import shutil
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from app.models.workspace_models import AttachmentInput
from app.services.attachment_processor import AttachmentProcessor, attachment_processor
from app.services import s3_storage_service as s3_module

_UPLOADS_DIR = Path("uploads")


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


def _fake_module(name: str, monkeypatch) -> types.ModuleType:
    mod = types.ModuleType(name)
    monkeypatch.setitem(sys.modules, name, mod)
    return mod


# ── process_attachments: top-level dispatch branches ──────────────────────────

@pytest.mark.asyncio
async def test_process_attachments_empty_list_returns_immediately():
    items, text, uris = await attachment_processor.process_attachments([], workspace_id=1)
    assert items == []
    assert text == ""
    assert uris == []


@pytest.mark.asyncio
async def test_process_attachments_unknown_type_is_skipped():
    attachments = [AttachmentInput(type="carrier-pigeon", name="x", url_or_data="abc")]
    items, text, uris = await attachment_processor.process_attachments(attachments, workspace_id=1)
    assert items == []
    assert text == ""


@pytest.mark.asyncio
async def test_process_attachments_pdf_dispatch():
    pdf_bytes = base64.b64encode(b"%PDF-1.4 fake pdf content").decode()
    attachments = [AttachmentInput(type="PDF", name="deck.pdf", url_or_data=pdf_bytes)]
    items, text, uris = await attachment_processor.process_attachments(attachments, workspace_id=1)
    assert len(items) == 1
    assert items[0].type == "pdf"
    assert "ATTACHED PDF DOCUMENT" in text


@pytest.mark.asyncio
async def test_process_attachments_image_without_uri_skips_uri_list():
    """Covers the branch where an image result has no image_data_uri."""
    proc = AttachmentProcessor()
    original = proc._process_image
    def _no_uri(*args, **kwargs):
        result = original(*args, **kwargs)
        result.image_data_uri = None
        return result
    proc._process_image = _no_uri

    attachments = [AttachmentInput(type="image", name="x.png", url_or_data="")]
    items, text, uris = await proc.process_attachments(attachments, workspace_id=1)
    assert len(items) == 1
    assert uris == []
    assert "ATTACHED IMAGE" in text


@pytest.mark.asyncio
async def test_process_attachments_catches_exception_and_records_error():
    proc = AttachmentProcessor()
    proc._process_pdf = MagicMock(side_effect=RuntimeError("boom"))

    attachments = [AttachmentInput(type="pdf", name="deck.pdf", url_or_data="abc")]
    items, text, uris = await proc.process_attachments(attachments, workspace_id=1)

    assert len(items) == 1
    assert items[0].error is not None
    assert "boom" in items[0].error


@pytest.mark.asyncio
async def test_process_attachments_doc_without_extracted_text_skips_context_block():
    proc = AttachmentProcessor()
    proc._process_doc = MagicMock(return_value=__import__(
        "app.services.attachment_processor", fromlist=["ProcessedAttachment"]
    ).ProcessedAttachment(type="doc", name="empty.txt", url=None, extracted_text=""))

    attachments = [AttachmentInput(type="doc", name="empty.txt", url_or_data="")]
    items, text, uris = await proc.process_attachments(attachments, workspace_id=1)
    assert len(items) == 1
    assert text == ""


# ── _process_pdf ────────────────────────────────────────────────────────────────

def test_process_pdf_without_pdfplumber_falls_back(monkeypatch):
    """pdfplumber isn't installed in this dev env — the import fails and the
    code should fall back to the placeholder text rather than crashing."""
    monkeypatch.setitem(sys.modules, "pdfplumber", None)  # force ImportError on `import pdfplumber`
    proc = AttachmentProcessor()
    result = proc._process_pdf(base64.b64encode(b"pdfbytes").decode(), "deck.pdf", workspace_id=1)
    assert result.type == "pdf"
    assert "Could not extract structured text" in result.extracted_text


def test_process_pdf_with_fake_pdfplumber_extracts_text(monkeypatch):
    fake_page = MagicMock()
    fake_page.extract_text.return_value = "Hello from page 1"
    fake_pdf_ctx = MagicMock()
    fake_pdf_ctx.__enter__.return_value.pages = [fake_page]
    fake_pdf_ctx.__exit__.return_value = False

    fake_pdfplumber = _fake_module("pdfplumber", monkeypatch)
    fake_pdfplumber.open = MagicMock(return_value=fake_pdf_ctx)

    proc = AttachmentProcessor()
    result = proc._process_pdf(base64.b64encode(b"pdfbytes").decode(), "deck.pdf", workspace_id=1)

    assert "Hello from page 1" in result.extracted_text
    assert "[Page 1]" in result.extracted_text


def test_process_pdf_empty_pages_uses_placeholder_text(monkeypatch):
    fake_page = MagicMock()
    fake_page.extract_text.return_value = ""
    fake_pdf_ctx = MagicMock()
    fake_pdf_ctx.__enter__.return_value.pages = [fake_page]
    fake_pdf_ctx.__exit__.return_value = False

    fake_pdfplumber = _fake_module("pdfplumber", monkeypatch)
    fake_pdfplumber.open = MagicMock(return_value=fake_pdf_ctx)

    proc = AttachmentProcessor()
    result = proc._process_pdf(base64.b64encode(b"pdfbytes").decode(), "deck.pdf", workspace_id=1)
    assert "PDF was empty" in result.extracted_text


def test_process_pdf_truncates_long_text(monkeypatch):
    fake_page = MagicMock()
    fake_page.extract_text.return_value = "x" * 9000
    fake_pdf_ctx = MagicMock()
    fake_pdf_ctx.__enter__.return_value.pages = [fake_page]
    fake_pdf_ctx.__exit__.return_value = False

    fake_pdfplumber = _fake_module("pdfplumber", monkeypatch)
    fake_pdfplumber.open = MagicMock(return_value=fake_pdf_ctx)

    proc = AttachmentProcessor()
    result = proc._process_pdf(base64.b64encode(b"pdfbytes").decode(), "deck.pdf", workspace_id=1)
    assert "Truncated due to length limit" in result.extracted_text
    assert len(result.extracted_text) < 9000


def test_process_pdf_appends_pdf_extension_when_missing():
    proc = AttachmentProcessor()
    result = proc._process_pdf(base64.b64encode(b"pdfbytes").decode(), "deck", workspace_id=1)
    assert result.url is not None


# ── _process_doc ──────────────────────────────────────────────────────────────

def test_process_doc_plain_text_extraction():
    proc = AttachmentProcessor()
    text = "Plain text business plan content."
    encoded = base64.b64encode(text.encode()).decode()
    result = proc._process_doc(encoded, "plan.txt", workspace_id=1, mime_type="text/plain")
    assert result.extracted_text == text


def test_process_doc_docx_without_python_docx_falls_back(monkeypatch):
    monkeypatch.setitem(sys.modules, "docx", None)
    proc = AttachmentProcessor()
    encoded = base64.b64encode(b"fake docx bytes").decode()
    result = proc._process_doc(encoded, "plan.docx", workspace_id=1)
    assert "Failed to parse DOCX structure" in result.extracted_text


def test_process_doc_docx_with_fake_python_docx_extracts_paragraphs(monkeypatch):
    fake_para1 = MagicMock(text="First paragraph.")
    fake_para2 = MagicMock(text="   ")  # blank, should be filtered out
    fake_document = MagicMock(paragraphs=[fake_para1, fake_para2])

    fake_docx = _fake_module("docx", monkeypatch)
    fake_docx.Document = MagicMock(return_value=fake_document)

    proc = AttachmentProcessor()
    encoded = base64.b64encode(b"fake docx bytes").decode()
    result = proc._process_doc(encoded, "plan.docx", workspace_id=1)
    assert result.extracted_text == "First paragraph."


def test_process_doc_detects_docx_via_mime_type(monkeypatch):
    fake_docx = _fake_module("docx", monkeypatch)
    fake_docx.Document = MagicMock(return_value=MagicMock(paragraphs=[]))

    proc = AttachmentProcessor()
    encoded = base64.b64encode(b"fake docx bytes").decode()
    proc._process_doc(
        encoded, "plan", workspace_id=1,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    fake_docx.Document.assert_called_once()


def test_process_doc_truncates_long_text():
    proc = AttachmentProcessor()
    long_text = "y" * 9000
    encoded = base64.b64encode(long_text.encode()).decode()
    result = proc._process_doc(encoded, "plan.txt", workspace_id=1)
    assert "Truncated due to length limit" in result.extracted_text


# ── _process_link ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_process_link_adds_https_prefix_when_missing(monkeypatch):
    async def _fake_get(self, url, headers=None):
        return httpx.Response(200, text="<html><body>hi</body></html>", request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    proc = AttachmentProcessor()
    result = await proc._process_link("example.com/page", "link")
    assert result.url == "https://example.com/page"


@pytest.mark.asyncio
async def test_process_link_non_200_status_records_message(monkeypatch):
    async def _fake_get(self, url, headers=None):
        return httpx.Response(404, text="not found", request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    proc = AttachmentProcessor()
    result = await proc._process_link("https://example.com/missing", "link")
    assert "HTTP 404" in result.extracted_text


@pytest.mark.asyncio
async def test_process_link_network_failure_records_message(monkeypatch):
    async def _fake_get(self, url, headers=None):
        raise httpx.ConnectTimeout("timed out")
    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    proc = AttachmentProcessor()
    result = await proc._process_link("https://unreachable.example.com", "link")
    assert "Could not load link content" in result.extracted_text


@pytest.mark.asyncio
async def test_process_link_without_beautifulsoup_falls_back_to_regex(monkeypatch):
    monkeypatch.setitem(sys.modules, "bs4", None)

    async def _fake_get(self, url, headers=None):
        return httpx.Response(200, text="<html><body><p>Hello World</p></body></html>", request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    proc = AttachmentProcessor()
    result = await proc._process_link("https://example.com", "link")
    assert "Hello World" in result.extracted_text
    assert "<p>" not in result.extracted_text


@pytest.mark.asyncio
async def test_process_link_with_fake_beautifulsoup_extracts_title_and_text(monkeypatch):
    fake_bs4 = _fake_module("bs4", monkeypatch)

    class _FakeTag:
        def __init__(self, text):
            self.string = text

    class _FakeSoup:
        def __init__(self, html, parser):
            self.title = _FakeTag("Page Title")

        def __call__(self, tags):
            return []

        def get_text(self, separator="\n"):
            return "Body\ntext\nhere"

    fake_bs4.BeautifulSoup = _FakeSoup

    async def _fake_get(self, url, headers=None):
        return httpx.Response(200, text="<html><head><title>Page Title</title></head></html>", request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    proc = AttachmentProcessor()
    result = await proc._process_link("https://example.com", "link")
    assert result.name == "Page Title"
    assert "Body" in result.extracted_text


@pytest.mark.asyncio
async def test_process_link_truncates_long_text(monkeypatch):
    async def _fake_get(self, url, headers=None):
        return httpx.Response(200, text="<html><body>" + ("z " * 4000) + "</body></html>", request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)
    monkeypatch.setitem(sys.modules, "bs4", None)

    proc = AttachmentProcessor()
    result = await proc._process_link("https://example.com", "link")
    assert "Truncated due to length limit" in result.extracted_text


# ── _process_image ──────────────────────────────────────────────────────────────

def test_process_image_with_data_uri_prefix_extracts_mime_type():
    proc = AttachmentProcessor()
    raw = "data:image/png;base64," + base64.b64encode(b"pngbytes").decode()
    result = proc._process_image(raw, "diagram", workspace_id=1)
    assert result.image_data_uri == raw
    assert result.type == "image"


def test_process_image_without_data_uri_detects_jpeg_from_filename():
    proc = AttachmentProcessor()
    raw = base64.b64encode(b"jpgbytes").decode()
    result = proc._process_image(raw, "photo.jpg", workspace_id=1)
    assert result.image_data_uri.startswith("data:image/jpeg;base64,")


def test_process_image_without_data_uri_defaults_to_png():
    proc = AttachmentProcessor()
    raw = base64.b64encode(b"pngbytes").decode()
    result = proc._process_image(raw, "diagram", workspace_id=1)
    assert result.image_data_uri.startswith("data:image/png;base64,")


# ── _decode_bytes ────────────────────────────────────────────────────────────────

def test_decode_bytes_strips_data_uri_prefix():
    proc = AttachmentProcessor()
    raw = "data:application/pdf;base64," + base64.b64encode(b"hello").decode()
    assert proc._decode_bytes(raw) == b"hello"


def test_decode_bytes_plain_base64_without_prefix():
    proc = AttachmentProcessor()
    raw = base64.b64encode(b"hello").decode()
    assert proc._decode_bytes(raw) == b"hello"


def test_decode_bytes_invalid_base64_falls_back_to_utf8_encode():
    proc = AttachmentProcessor()
    raw = "not valid base64!!! but plain text"
    assert proc._decode_bytes(raw) == raw.encode("utf-8")
