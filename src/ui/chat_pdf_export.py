"""
Chat history PDF export for LexAI.

Generates a professional PDF of the conversation using ReportLab.
Uses shared font and escape helpers from services.case_law.pdf_shared.
"""

from datetime import datetime
from io import BytesIO

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from src.services.case_law.pdf_shared import escape_for_reportlab, register_and_get_fonts

_FONT, _FONT_BOLD, _ = register_and_get_fonts()

_PRIMARY = HexColor("#1e3a5f")
_ACCENT = HexColor("#2563eb")
_DARK = HexColor("#222222")
_GREY = HexColor("#666666")
_HR_COLOR = HexColor("#e2e8f0")


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
        "section_heading": ParagraphStyle(
            "SectionHeading",
            fontName=_FONT_BOLD,
            fontSize=11,
            leading=14,
            spaceBefore=8,
            spaceAfter=4,
            textColor=_PRIMARY,
        ),
        "case_heading": ParagraphStyle(
            "CaseHeading",
            fontName=_FONT_BOLD,
            fontSize=10,
            leading=13,
            spaceBefore=6,
            spaceAfter=2,
            textColor=_ACCENT,
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


_SECTION_KEYWORDS = frozenset(
    {
        "legal position summary",
        "precedent analysis",
        "trend & development",
        "trend and development",
        "practical implications",
        "applicable legislation",
        "oikeudellinen yhteenveto",
        "ennakkopäätösanalyysi",
        "kehityssuunta",
        "käytännön vaikutukset",
        "sovellettava lainsäädäntö",
    }
)

_CASE_ID_PREFIXES = ("KKO:", "KHO:", "ECLI:")


def _pick_paragraph_style(text: str, styles: dict) -> ParagraphStyle:
    """Choose the right PDF style based on line content."""
    stripped = text.lstrip("#").strip()
    lower = stripped.lower()
    if text.startswith("#") or lower in _SECTION_KEYWORDS:
        return styles["section_heading"]
    if stripped.startswith(_CASE_ID_PREFIXES):
        return styles["case_heading"]
    return styles["message"]


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
    story.append(Paragraph(escape_for_reportlab(title), styles["title"]))
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    story.append(Paragraph(escape_for_reportlab(f"Generated: {timestamp}"), styles["subtitle"]))
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

        for raw_para in content.split("\n"):
            para = raw_para.strip()
            if not para:
                continue
            style = _pick_paragraph_style(para, styles)
            display = para.lstrip("#").strip() if para.startswith("#") else para
            story.append(Paragraph(escape_for_reportlab(display), style))

        story.append(HRFlowable(width="100%", thickness=0.5, color=_HR_COLOR, spaceBefore=4, spaceAfter=4))

    # Footer
    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            escape_for_reportlab(f"LexAI - Finnish Legal AI Assistant | {timestamp}"),
            styles["footer"],
        )
    )

    doc.build(story)
    return buffer.getvalue()
