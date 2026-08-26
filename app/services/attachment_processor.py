"""
app/services/attachment_processor.py
────────────────────────────────────────────────────────────────────────────────
Attachment Processor Service for Mentor Chat API.
Parses, stores, and extracts content from:
  1. PDFs (using pdfplumber)
  2. Documents (.docx using python-docx, .txt, .md)
  3. Web Links (using httpx + BeautifulSoup)
  4. Images (decodes, uploads to S3/local, formats for Vision LLM)
"""
import base64
import io
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx
from pydantic import BaseModel

from app.db.models import WorkspaceAttachment
from app.models.workspace_models import AttachmentInput
from app.services.s3_storage_service import s3_storage_service

logger = logging.getLogger(__name__)


class ProcessedAttachment(BaseModel):
    type: str  # image | pdf | doc | link
    name: str
    url: Optional[str] = None
    s3_key: Optional[str] = None
    extracted_text: Optional[str] = None
    image_data_uri: Optional[str] = None
    error: Optional[str] = None


class AttachmentProcessor:

    async def process_attachments(
        self,
        attachments: List[AttachmentInput],
        workspace_id: str | int,
        user_id: Optional[int | str] = None,
        db: Optional[Any] = None,
    ) -> Tuple[List[ProcessedAttachment], str, List[str]]:
        """
        Process a list of incoming attachment inputs.
        Returns:
          - processed_items: List of ProcessedAttachment objects with metadata & S3 URLs
          - formatted_text_context: Combined text extracted from PDFs, Docs, Links for LLM prompt
          - image_data_uris: List of base64 data URIs for vision-capable LLM calls
        """
        processed_items: List[ProcessedAttachment] = []
        text_context_blocks: List[str] = []
        image_data_uris: List[str] = []

        if not attachments:
            return processed_items, "", image_data_uris

        logger.info(
            "[AttachmentProcessor] Processing %s attachment(s) for workspace %s (user_id=%s)",
            len(attachments), workspace_id, user_id,
        )

        for idx, item in enumerate(attachments, start=1):
            att_type = (item.type or "").lower().strip()
            name = item.name or f"Attachment_{idx}"
            raw_data = item.url_or_data or ""

            try:
                if att_type == "pdf":
                    res = self._process_pdf(raw_data, name, workspace_id, user_id=user_id)
                    processed_items.append(res)
                    if res.extracted_text:
                        text_context_blocks.append(
                            f"--- ATTACHED PDF DOCUMENT: {res.name} (URL: {res.url or 'N/A'}) ---\n"
                            f"{res.extracted_text}\n"
                            f"--- END ATTACHED PDF DOCUMENT ---"
                        )

                elif att_type == "doc":
                    res = self._process_doc(raw_data, name, workspace_id, item.mime_type, user_id=user_id)
                    processed_items.append(res)
                    if res.extracted_text:
                        text_context_blocks.append(
                            f"--- ATTACHED DOCUMENT: {res.name} (URL: {res.url or 'N/A'}) ---\n"
                            f"{res.extracted_text}\n"
                            f"--- END ATTACHED DOCUMENT ---"
                        )

                elif att_type == "link":
                    res = await self._process_link(raw_data, name)
                    processed_items.append(res)
                    if res.extracted_text:
                        text_context_blocks.append(
                            f"--- ATTACHED LINK CONTENT: {res.name} (URL: {res.url}) ---\n"
                            f"{res.extracted_text}\n"
                            f"--- END ATTACHED LINK ---"
                        )

                elif att_type == "image":
                    res = self._process_image(raw_data, name, workspace_id, user_id=user_id)
                    processed_items.append(res)
                    if res.image_data_uri:
                        image_data_uris.append(res.image_data_uri)
                    text_context_blocks.append(
                        f"--- ATTACHED IMAGE: {res.name} (URL: {res.url or 'N/A'}) ---"
                    )

                else:
                    logger.warning("[AttachmentProcessor] Unknown attachment type '%s'", att_type)

            except Exception as e:
                logger.exception("[AttachmentProcessor] Error processing attachment '%s': %s", name, e)
                processed_items.append(
                    ProcessedAttachment(
                        type=att_type,
                        name=name,
                        error=f"Failed to process attachment: {str(e)}"
                    )
                )

        # Sync persisted WorkspaceAttachment database records if db session and user_id are available
        if db and user_id:
            try:
                for res in processed_items:
                    if res.type in ("pdf", "doc", "image") and res.url and res.s3_key and not res.error:
                        file_mime = "application/pdf" if res.type == "pdf" else (
                            "image/jpeg" if res.name.lower().endswith((".jpg", ".jpeg")) else (
                                "image/png" if res.type == "image" else "application/octet-stream"
                            )
                        )
                        att_record = WorkspaceAttachment(
                            user_id=int(user_id),
                            workspace_id=int(workspace_id),
                            file_name=res.name,
                            file_type=res.type,
                            mime_type=file_mime,
                            s3_key=res.s3_key,
                            file_url=res.url,
                            file_size_bytes=None,
                        )
                        db.add(att_record)
                await db.flush()
            except Exception as db_err:
                logger.warning("[AttachmentProcessor] Could not sync WorkspaceAttachment DB record: %s", db_err)

        formatted_context = "\n\n".join(text_context_blocks)
        return processed_items, formatted_context, image_data_uris

    def _process_pdf(
        self,
        raw_data: str,
        name: str,
        workspace_id: str | int,
        user_id: Optional[int | str] = None,
    ) -> ProcessedAttachment:
        """Extract text from PDF using pdfplumber and upload PDF to axiora-assets bucket."""
        file_bytes = self._decode_bytes(raw_data)
        safe_name = name if name.endswith(".pdf") else f"{name}.pdf"
        file_url, s3_key = s3_storage_service.upload_workspace_asset(
            file_bytes=file_bytes,
            filename=safe_name,
            user_id=user_id or 1,
            workspace_id=workspace_id,
            file_type="pdf",
            content_type="application/pdf",
        )

        extracted_pages = []
        try:
            import pdfplumber

            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for p_num, page in enumerate(pdf.pages, start=1):
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        extracted_pages.append(f"[Page {p_num}]\n{page_text.strip()}")
        except Exception as e:
            logger.warning("[AttachmentProcessor] pdfplumber extraction failed for %s: %s. Falling back to simple reader.", safe_name, e)
            # Simple fallback text extraction if pdfplumber fails
            extracted_pages.append("(Could not extract structured text from PDF file)")

        full_text = "\n\n".join(extracted_pages) if extracted_pages else "(PDF was empty or contained only non-extractable raster images)"
        # Cap text length to prevent prompt overflow
        if len(full_text) > 8000:
            full_text = full_text[:8000] + "\n... [Truncated due to length limit]"

        return ProcessedAttachment(
            type="pdf",
            name=name,
            url=file_url,
            s3_key=s3_key,
            extracted_text=full_text,
        )

    def _process_doc(
        self,
        raw_data: str,
        name: str,
        workspace_id: str | int,
        mime_type: Optional[str] = None,
        user_id: Optional[int | str] = None,
    ) -> ProcessedAttachment:
        """Extract text from .docx (using python-docx) or text/markdown files and upload to axiora-assets bucket."""
        file_bytes = self._decode_bytes(raw_data)
        file_url, s3_key = s3_storage_service.upload_workspace_asset(
            file_bytes=file_bytes,
            filename=name,
            user_id=user_id or 1,
            workspace_id=workspace_id,
            file_type="doc",
            content_type=mime_type or "application/octet-stream",
        )

        extracted_text = ""
        is_docx = name.endswith(".docx") or (mime_type and "wordprocessingml" in mime_type)

        if is_docx:
            try:
                import docx

                doc = docx.Document(io.BytesIO(file_bytes))
                paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                extracted_text = "\n".join(paragraphs)
            except Exception as e:
                logger.warning("[AttachmentProcessor] docx extraction failed for %s: %s", name, e)
                extracted_text = "(Failed to parse DOCX structure)"
        else:
            try:
                extracted_text = file_bytes.decode("utf-8", errors="ignore")
            except Exception as e:
                extracted_text = f"(Failed to decode text document: {e})"

        if len(extracted_text) > 8000:
            extracted_text = extracted_text[:8000] + "\n... [Truncated due to length limit]"

        return ProcessedAttachment(
            type="doc",
            name=name,
            url=file_url,
            s3_key=s3_key,
            extracted_text=extracted_text,
        )

    async def _process_link(self, link_url: str, name: str) -> ProcessedAttachment:
        """Fetch and extract text content from a web URL using httpx + BeautifulSoup."""
        clean_url = link_url.strip()
        if not clean_url.startswith(("http://", "https://")):
            clean_url = f"https://{clean_url}"

        title = name if name and name != "link" else clean_url
        extracted_text = ""

        try:
            async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
                resp = await client.get(clean_url, headers={"User-Agent": "AxioraPulseBot/1.0"})
                if resp.status_code == 200:
                    html_content = resp.text
                    try:
                        from bs4 import BeautifulSoup

                        soup = BeautifulSoup(html_content, "html.parser")

                        # Extract title if available
                        if soup.title and soup.title.string:
                            title = soup.title.string.strip()

                        # Remove script/style tags
                        for tag in soup(["script", "style", "nav", "footer", "header"]):
                            tag.decompose()

                        text = soup.get_text(separator="\n")
                        lines = [line.strip() for line in text.splitlines() if line.strip()]
                        extracted_text = "\n".join(lines)
                    except Exception as bs_err:
                        logger.warning("[AttachmentProcessor] BeautifulSoup parsing error for %s: %s", clean_url, bs_err)
                        # Fallback simple regex strip
                        extracted_text = re.sub(r"<[^>]+>", " ", html_content)
                else:
                    extracted_text = f"(HTTP {resp.status_code} response when fetching link content)"
        except Exception as e:
            logger.warning("[AttachmentProcessor] Failed to fetch link %s: %s", clean_url, e)
            extracted_text = f"(Could not load link content: {str(e)})"

        if len(extracted_text) > 6000:
            extracted_text = extracted_text[:6000] + "\n... [Truncated due to length limit]"

        return ProcessedAttachment(
            type="link",
            name=title,
            url=clean_url,
            extracted_text=extracted_text,
        )

    def _process_image(
        self,
        raw_data: str,
        name: str,
        workspace_id: str | int,
        user_id: Optional[int | str] = None,
    ) -> ProcessedAttachment:
        """Decode base64 image (JPEG, JPG, PNG, WEBP, GIF, etc.), upload to axiora-assets, and prepare base64 data URI for Vision LLM."""
        mime_type = "image/jpeg" if name.lower().endswith((".jpg", ".jpeg")) else "image/png"

        if raw_data.startswith("data:image/"):
            header = raw_data.split(";")[0]
            mime_type = header.replace("data:", "")
            data_uri = raw_data
        else:
            if "jpeg" in name.lower() or "jpg" in name.lower():
                mime_type = "image/jpeg"
            data_uri = f"data:{mime_type};base64,{raw_data}"

        ext = ".jpg" if "jpeg" in mime_type or "jpg" in mime_type else ".png"
        safe_name = name if "." in name else f"{name}{ext}"
        file_bytes = self._decode_bytes(raw_data)

        file_url, s3_key = s3_storage_service.upload_workspace_asset(
            file_bytes=file_bytes,
            filename=safe_name,
            user_id=user_id or 1,
            workspace_id=workspace_id,
            file_type="image",
            content_type=mime_type,
        )

        return ProcessedAttachment(
            type="image",
            name=name,
            url=file_url,
            s3_key=s3_key,
            image_data_uri=data_uri,
        )


    def _decode_bytes(self, raw_data: str) -> bytes:
        """Helper to extract raw bytes from a base64 string or plain text."""
        if "," in raw_data:
            _, base64_str = raw_data.split(",", 1)
        else:
            base64_str = raw_data

        try:
            return base64.b64decode(base64_str)
        except Exception:
            return raw_data.encode("utf-8")


attachment_processor = AttachmentProcessor()
