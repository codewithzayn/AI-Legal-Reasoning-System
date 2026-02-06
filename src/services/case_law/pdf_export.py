# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL. Unauthorized copying, distribution, or use is strictly prohibited.

"""
Case law PDF export: convert CaseLawDocument full_text to a readable PDF (Finnish-safe).
Used by the separate backup pipeline only.
"""

import re
from pathlib import Path
from typing import Optional, Union

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT

from src.services.case_law.scraper import CaseLawDocument
from src.config.logging_config import setup_logger

logger = setup_logger(__name__)

# Try to register a font that supports Finnish (ä, ö, Å). Use DejaVu if available, else fallback.
def _register_fonts():
    try:
        import reportlab.pdfbase.cidfonts
        # Helvetica supports Latin-1; for full Finnish use a TTF. DejaVu is often installed.
        for name, path in [
            ("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            ("DejaVuSans", "/usr/share/fonts/dejavu/DejaVuSans.ttf"),
        ]:
            if Path(path).exists():
                pdfmetrics.registerFont(TTFont("DejaVuSans", path))
                return "DejaVuSans"
    except Exception:
        pass
    return "Helvetica"


_FINNISH_FONT = _register_fonts()


def _sanitize_filename(case_id: Optional[str]) -> str:
    """Sanitize case_id for use as filename (e.g. KKO:2025:1 -> KKO-2025-1.pdf)."""
    if not (case_id or "").strip():
        return "unknown"
    return re.sub(r'[^\w\-.]', '-', (case_id or "").strip()).strip("-") or "case"


def doc_to_pdf(doc: Optional[CaseLawDocument]) -> bytes:
    """
    Convert a CaseLawDocument to PDF bytes. Uses full_text; supports Finnish (ä, ö, Å).
    Raises ValueError if doc is None.
    """
    from io import BytesIO
    if doc is None:
        raise ValueError("doc must not be None")
    buffer = BytesIO()
    text = (getattr(doc, "full_text", None) or "").strip()
    case_id = getattr(doc, "case_id", None) or "unknown"
    if not text:
        text = f"No content for {case_id}."

    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        name="Body",
        parent=styles["Normal"],
        fontName=_FINNISH_FONT,
        fontSize=10,
        leading=12,
        alignment=TA_LEFT,
    )
    title_style = ParagraphStyle(
        name="DocTitle",
        parent=styles["Heading1"],
        fontName=_FINNISH_FONT,
        fontSize=14,
        spaceAfter=6,
    )

    doc_template = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    story = []
    story.append(Paragraph(_escape(case_id), title_style))
    story.append(Spacer(1, 6))

    # Split into paragraphs; preserve line breaks and avoid overly long lines for PDF
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        para_text = _escape(block.replace("\n", "<br/>"))
        story.append(Paragraph(para_text, body_style))
        story.append(Spacer(1, 4))

    doc_template.build(story)
    return buffer.getvalue()


def _escape(s: str) -> str:
    """Escape for ReportLab Paragraph (XML-style)."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def write_pdf_for_document(doc: Optional[CaseLawDocument], output_path: Union[str, Path]) -> Path:
    """
    Generate PDF for doc and write to output_path. Returns the path written.
    Raises ValueError if doc is None.
    """
    if doc is None:
        raise ValueError("doc must not be None")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf_bytes = doc_to_pdf(doc)
    path.write_bytes(pdf_bytes)
    logger.debug("Wrote PDF %s (%s bytes)", path, len(pdf_bytes))
    return path


def get_pdf_filename(case_id: Optional[str]) -> str:
    """Return the PDF filename for a case_id (e.g. KKO-2025-1.pdf). Handles None/empty."""
    return _sanitize_filename(case_id) + ".pdf"
