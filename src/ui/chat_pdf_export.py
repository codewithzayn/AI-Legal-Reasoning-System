"""
Chat history PDF export for LexAI.

Generates a professional PDF of the conversation using ReportLab,
reusing font registration and escape patterns from pdf_export.py.
"""

from datetime import datetime
from io import BytesIO
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

# Font setup (same as pdf_export.py)
_FONT = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"


def _register_fonts() -> None:
    """Register DejaVuSans if available (Finnish character support)."""
    global _FONT, _FONT_BOLD  # noqa: PLW0603
    font_dirs = [
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts/dejavu",
    ]
    for font_dir in font_dirs:
        regular = Path(font_dir) / "DejaVuSans.ttf"
        bold = Path(font_dir) / "DejaVuSans-Bold.ttf"
        if regular.exists():
            pdfmetrics.registerFont(TTFont("DejaVuSans", str(regular)))
            _FONT = "DejaVuSans"
            if bold.exists():
                pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(bold)))
                _FONT_BOLD = "DejaVuSans-Bold"
            return


_register_fonts()

_PRIMARY = HexColor("#1e3a5f")
_ACCENT = HexColor("#2563eb")
_DARK = HexColor("#222222")
_GREY = HexColor("#666666")
_LIGHT_BG = HexColor("#f8fafc")
_HR_COLOR = HexColor("#e2e8f0")


def _escape(s: str) -> str:
    """Escape for ReportLab Paragraph XML."""
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _build_styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle(
            "ChatTitle",
            fontName=_FONT_BOLD,
            fontSize=16,
            leading=20,
            spaceAfter=4,
            textColor=_PRIMARY,
            alignment=TA_CENTER,
        ),
        "subtitle": ParagraphStyle(
            "ChatSubtitle",
            fontName=_FONT,
            fontSize=9,
            leading=12,
            spaceAfter=12,
            textColor=_GREY,
            alignment=TA_CENTER,
        ),
        "user_label": ParagraphStyle(
            "UserLabel",
            fontName=_FONT_BOLD,
            fontSize=10,
            leading=13,
            spaceBefore=10,
            spaceAfter=2,
            textColor=_ACCENT,
        ),
        "assistant_label": ParagraphStyle(
            "AssistantLabel",
            fontName=_FONT_BOLD,
            fontSize=10,
            leading=13,
            spaceBefore=10,
            spaceAfter=2,
            textColor=_PRIMARY,
        ),
        "message": ParagraphStyle(
            "Message",
            fontName=_FONT,
            fontSize=9.5,
            leading=13,
            spaceBefore=0,
            spaceAfter=6,
            textColor=_DARK,
            alignment=TA_LEFT,
        ),
        "footer": ParagraphStyle(
            "Footer",
            fontName=_FONT,
            fontSize=7.5,
            leading=10,
            textColor=_GREY,
            alignment=TA_CENTER,
        ),
    }


def generate_chat_pdf(messages: list[dict], title: str = "LexAI Chat Export") -> bytes:
    """Generate a PDF from chat messages.

    Args:
        messages: List of {"role": "user"|"assistant", "content": "..."} dicts.
        title: PDF title header.

    Returns:
        PDF bytes.
    """
    buffer = BytesIO()
    styles = _build_styles()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    story: list = []

    # Header
    story.append(Paragraph(_escape(title), styles["title"]))
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    story.append(Paragraph(_escape(f"Generated: {timestamp}"), styles["subtitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=_HR_COLOR, spaceBefore=4, spaceAfter=8))

    # Messages
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if not content:
            continue

        if role == "user":
            story.append(Paragraph("\U0001f464 User", styles["user_label"]))
        else:
            story.append(Paragraph("\u2696\ufe0f LexAI", styles["assistant_label"]))

        # Split long content into paragraphs
        for raw_para in content.split("\n"):
            para = raw_para.strip()
            if para:
                story.append(Paragraph(_escape(para), styles["message"]))

        story.append(HRFlowable(width="100%", thickness=0.5, color=_HR_COLOR, spaceBefore=4, spaceAfter=4))

    # Footer
    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            _escape(f"LexAI - Finnish Legal AI Assistant | {timestamp}"),
            styles["footer"],
        )
    )

    doc.build(story)
    return buffer.getvalue()
