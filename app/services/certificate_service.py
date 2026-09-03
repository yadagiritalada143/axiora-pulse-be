"""
Certificate of Completion generator for Axiora Pulse.

Renders the user's name onto the branded certificate template PDF
using the Alex Brush font in gold.
"""
from __future__ import annotations

import logging
from pathlib import Path

import fitz

logger = logging.getLogger(__name__)

_CERTIFICATE_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1] / "templates" / "idea_validation_certificate_template.pdf"
)
_ALEX_BRUSH_FONT_PATH = (
    Path(__file__).resolve().parents[1] / "templates" / "fonts" / "AlexBrush-Regular.ttf"
)

# Gold colour (RGB 0–1)
_GOLD = (0.831, 0.686, 0.216)
_FONT_SIZE = 63


class CertificateService:
    """Generates a personalised Certificate of Completion PDF."""

    def generate_certificate(self, display_name: str) -> bytes:
        """
        Open the certificate template, draw *display_name* centred on
        the first page, and return the resulting PDF as raw bytes.
        """
        fontfile = str(_ALEX_BRUSH_FONT_PATH) if _ALEX_BRUSH_FONT_PATH.exists() else None
        if fontfile is None:
            logger.error("Alex Brush font not found at %s", _ALEX_BRUSH_FONT_PATH)
            raise FileNotFoundError(f"Certificate font missing: {_ALEX_BRUSH_FONT_PATH}")

        doc = fitz.open(str(_CERTIFICATE_TEMPLATE_PATH))
        try:
            page = doc[0]
            rect = page.rect  # full page dimensions

            # Measure text width so we can centre it horizontally
            font_obj = fitz.Font(fontfile=fontfile)
            text_width = font_obj.text_length(display_name, fontsize=_FONT_SIZE)

            line_center_x = rect.width * 0.575  # center of the line on the certificate
            x = line_center_x - (text_width / 2)
            y = rect.height * 0.485  # name baseline at ~48.5% (above the line at ~51%)

            page.insert_text(
                fitz.Point(x, y),
                display_name,
                fontname="AlexBrush",
                fontfile=fontfile,
                fontsize=_FONT_SIZE,
                color=_GOLD,
            )

            pdf_bytes: bytes = doc.tobytes()
        finally:
            doc.close()

        logger.info(
            "Certificate generated for '%s': %d bytes", display_name, len(pdf_bytes)
        )
        return pdf_bytes


certificate_service = CertificateService()
