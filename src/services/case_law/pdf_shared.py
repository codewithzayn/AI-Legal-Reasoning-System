"""
Shared ReportLab helpers for PDF generation (case law and chat export).

Provides font registration (Finnish-safe DejaVu) and XML-style escaping
for Paragraph content. Single place to avoid duplication.
"""

from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_FONT_CACHE: tuple[str, str, str] | None = None


def register_and_get_fonts() -> tuple[str, str, str]:
    """
    Register DejaVuSans (and Bold, Oblique) if available; return (font, font_bold, font_italic).
    Safe for Finnish (ä, ö, Å). Call once per process; returns cached tuple after first call.
    """
    global _FONT_CACHE  # noqa: PLW0603
    if _FONT_CACHE is not None:
        return _FONT_CACHE
    font = "Helvetica"
    font_bold = "Helvetica-Bold"
    font_italic = "Helvetica-Oblique"
    font_dirs = [
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts/dejavu",
    ]
    for font_dir in font_dirs:
        regular = Path(font_dir) / "DejaVuSans.ttf"
        bold = Path(font_dir) / "DejaVuSans-Bold.ttf"
        oblique = Path(font_dir) / "DejaVuSans-Oblique.ttf"
        if regular.exists():
            pdfmetrics.registerFont(TTFont("DejaVuSans", str(regular)))
            font = "DejaVuSans"
            if bold.exists():
                pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(bold)))
                font_bold = "DejaVuSans-Bold"
            if oblique.exists():
                pdfmetrics.registerFont(TTFont("DejaVuSans-Oblique", str(oblique)))
                font_italic = "DejaVuSans-Oblique"
            break
    _FONT_CACHE = (font, font_bold, font_italic)
    return _FONT_CACHE


def escape_for_reportlab(s: str) -> str:
    """Escape for ReportLab Paragraph (XML-style; prevents injection in PDF content)."""
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
