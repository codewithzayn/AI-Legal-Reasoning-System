# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL. Unauthorized copying, distribution, or use is strictly prohibited.

"""
Case law PDF export: convert CaseLawDocument to a professionally formatted PDF
that mirrors the Finlex website layout (metadata header, section headings,
numbered paragraphs, judge attribution). Supports Finnish (ä, ö, Å).

Used by the separate backup pipeline only.
"""

import re
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from src.config.logging_config import setup_logger
from src.services.case_law.scraper import CaseLawDocument

logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
#  Font registration (Finnish-safe: DejaVu + Bold variant)
# ---------------------------------------------------------------------------

_FONT = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_FONT_ITALIC = "Helvetica-Oblique"


def _register_fonts() -> None:
    """Register DejaVuSans + Bold if available (supports Finnish ä, ö, Å)."""
    global _FONT, _FONT_BOLD, _FONT_ITALIC  # noqa: PLW0603
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
            _FONT = "DejaVuSans"
            if bold.exists():
                pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(bold)))
                _FONT_BOLD = "DejaVuSans-Bold"
            if oblique.exists():
                pdfmetrics.registerFont(TTFont("DejaVuSans-Oblique", str(oblique)))
                _FONT_ITALIC = "DejaVuSans-Oblique"
            return


_register_fonts()

# ---------------------------------------------------------------------------
#  Color constants
# ---------------------------------------------------------------------------
_GREY = HexColor("#666666")
_DARK = HexColor("#222222")
_HR_COLOR = HexColor("#cccccc")

# ---------------------------------------------------------------------------
#  Styles
# ---------------------------------------------------------------------------


def _build_styles() -> dict[str, ParagraphStyle]:
    """Build all PDF paragraph styles."""
    return {
        "title": ParagraphStyle(
            "DocTitle",
            fontName=_FONT_BOLD,
            fontSize=16,
            leading=20,
            spaceAfter=8,
            textColor=_DARK,
            alignment=TA_LEFT,
        ),
        "meta_label": ParagraphStyle(
            "MetaLabel",
            fontName=_FONT_BOLD,
            fontSize=9,
            leading=12,
            textColor=_GREY,
            alignment=TA_LEFT,
        ),
        "meta_value": ParagraphStyle(
            "MetaValue",
            fontName=_FONT,
            fontSize=9,
            leading=12,
            textColor=_DARK,
            alignment=TA_LEFT,
        ),
        "section_heading": ParagraphStyle(
            "SectionHeading",
            fontName=_FONT_BOLD,
            fontSize=12,
            leading=16,
            spaceBefore=14,
            spaceAfter=6,
            textColor=_DARK,
            alignment=TA_LEFT,
        ),
        "sub_heading": ParagraphStyle(
            "SubHeading",
            fontName=_FONT_BOLD,
            fontSize=10.5,
            leading=14,
            spaceBefore=10,
            spaceAfter=4,
            textColor=_DARK,
            alignment=TA_LEFT,
        ),
        "body": ParagraphStyle(
            "Body",
            fontName=_FONT,
            fontSize=10,
            leading=13,
            spaceBefore=2,
            spaceAfter=4,
            textColor=_DARK,
            alignment=TA_LEFT,
        ),
        "numbered": ParagraphStyle(
            "Numbered",
            fontName=_FONT,
            fontSize=10,
            leading=13,
            spaceBefore=2,
            spaceAfter=4,
            textColor=_DARK,
            alignment=TA_LEFT,
            leftIndent=8 * mm,
            firstLineIndent=-8 * mm,
        ),
        "law_ref": ParagraphStyle(
            "LawRef",
            fontName=_FONT_ITALIC,
            fontSize=10,
            leading=13,
            spaceBefore=4,
            spaceAfter=6,
            textColor=_DARK,
            alignment=TA_LEFT,
        ),
        "judge_line": ParagraphStyle(
            "JudgeLine",
            fontName=_FONT_ITALIC,
            fontSize=9,
            leading=12,
            spaceBefore=4,
            spaceAfter=2,
            textColor=_GREY,
            alignment=TA_LEFT,
        ),
        "footer_note": ParagraphStyle(
            "FooterNote",
            fontName=_FONT,
            fontSize=8,
            leading=10,
            textColor=_GREY,
            alignment=TA_CENTER,
        ),
    }


# ---------------------------------------------------------------------------
#  Section detection patterns (Finnish + English)
# ---------------------------------------------------------------------------

# Major section headings (rendered in bold, larger font)
_SECTION_HEADINGS = [
    re.compile(
        r"^(?:Asian käsittely alemmissa oikeuksissa|Hearing of the case in lower courts|Previous handling of the case)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:Muutoksenhaku Korkeimmassa oikeudessa|Appeal to the Supreme Court|Additional appeal to the Supreme Court)$",
        re.IGNORECASE,
    ),
    re.compile(r"^(?:Korkeimman oikeuden ratkaisu|Supreme Court decision)$", re.IGNORECASE),
]

# Sub-headings (rendered bold, slightly smaller)
_SUB_HEADINGS = [
    re.compile(r"^(?:Perustelut|Reasoning)$", re.IGNORECASE),
    re.compile(r"^(?:Tuomiolauselma|Judgment)$", re.IGNORECASE),
    re.compile(r"^(?:Johtopäätös|Conclusion|Evaluation and conclusions|Arviointi ja johtopäätökset)$", re.IGNORECASE),
]

# Court judgment sub-headings (e.g. "Kymenlaakson käräjäoikeuden tuomio 20.4.2023 nro 23/116279")
_COURT_JUDGMENT = re.compile(
    r"^(?:.*(?:käräjäoikeuden|hovioikeuden|District Court|Court of Appeal)\s+(?:tuomio|judgment|päätös|decision))",
    re.IGNORECASE,
)

# Sub-section title within Reasoning (short line before numbered paragraphs)
_REASONING_SUBSECTION = re.compile(
    r"^(?:Asian tausta|Onko kysymys|Background|Starting points|Evaluation|Arviointi|Kieltoerehdys|Prohibition error|Rikosoikeudellinen laillisuusperiaate|Criminal legality|Oliko kysymys|Was the issue)",
    re.IGNORECASE,
)

# Numbered paragraph: "1. text..." or "22. text..."
_NUMBERED = re.compile(r"^\d{1,3}\.\s+\S")

# Law reference line: "RL 46 luku..." or statute citation
_LAW_REF = re.compile(
    r"^(?:RL|Rikoslaki|Criminal Code|Oikeudenkäymiskaari|Code of Judicial Procedure)\s+\d+", re.IGNORECASE
)

# Judge attribution
_JUDGE_LINE = re.compile(
    r"^(?:Asian (?:ovat|on) ratkaiss\w+|The (?:case|matter) has been (?:resolved|decided))\s+",
    re.IGNORECASE,
)
_RAPPORTEUR_LINE = re.compile(r"^(?:Esittelijä|Rapporteur)\s+", re.IGNORECASE)

# Metadata header labels to strip from body (already rendered in the header block)
_HEADER_NOISE = {
    "Kieliversiot",
    "Language versions",
    "Suomi",
    "Ruotsi",
    "Finnish",
    "Swedish",
    "Kopioi ECLI-linkki",
    "Copy ECLI link",
    "Asiasanat",
    "Keywords",
    "Tapausvuosi",
    "Case year",
    "Antopäivä",
    "Date of issue",
    "Diaarinumero",
    "Diary number",
    "Taltio",
    "Volume",
    "ECLI-tunnus",
    "ECLI code",
}


# ---------------------------------------------------------------------------
#  Header metadata parsing from full_text (for PDF rendering)
# ---------------------------------------------------------------------------


def _parse_metadata_from_text(text: str) -> dict:
    """
    Parse the structured header block from full_text to extract metadata.
    Returns dict with keywords, decision_date, diary_number, volume, ecli,
    and body_start (line index where the main content begins).
    """
    lines = text.split("\n")
    result: dict = {"keywords": [], "body_start": 0}

    current_field = None
    label_map = {
        "Asiasanat": "keywords",
        "Keywords": "keywords",
        "Antopäivä": "decision_date",
        "Date of issue": "decision_date",
        "Diaarinumero": "diary_number",
        "Diary number": "diary_number",
        "Taltio": "volume",
        "Volume": "volume",
        "ECLI-tunnus": "ecli",
        "ECLI code": "ecli",
        "Tapausvuosi": "case_year",
        "Case year": "case_year",
    }

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        if line in _HEADER_NOISE or line in label_map:
            current_field = label_map.get(line)
            continue
        if current_field:
            if current_field == "keywords":
                result["keywords"].append(line)
            elif current_field not in result:
                result[current_field] = line
            if current_field != "keywords":
                current_field = None
            continue
        # First long line or section heading = body start
        if i > 3 and (len(line) > 60 or _LAW_REF.match(line)):
            result["body_start"] = i
            break
        # Skip the case_id line at the very top (e.g. "KKO:2026:1")
    return result


def _get_body_lines(text: str, body_start: int) -> list[str]:
    """Return the main content lines (after stripping the metadata header)."""
    lines = text.split("\n")
    return lines[body_start:]


# ---------------------------------------------------------------------------
#  Classify each line for styling
# ---------------------------------------------------------------------------


def _classify_line(line: str) -> str:
    """Classify a text line into a style category."""
    stripped = line.strip()
    if not stripped:
        return "blank"
    if any(pat.match(stripped) for pat in _SECTION_HEADINGS):
        return "section_heading"
    if any(pat.match(stripped) for pat in _SUB_HEADINGS):
        return "sub_heading"
    if _COURT_JUDGMENT.match(stripped):
        return "sub_heading"
    # Patterns checked via a mapping to avoid too many return statements
    checks = [
        (_JUDGE_LINE, "judge_line"),
        (_RAPPORTEUR_LINE, "judge_line"),
        (_NUMBERED, "numbered"),
        (_LAW_REF, "law_ref"),
    ]
    for pat, category in checks:
        if pat.match(stripped):
            return category
    if _REASONING_SUBSECTION.match(stripped) and len(stripped) < 120:
        return "sub_heading"
    return "body"


# ---------------------------------------------------------------------------
#  Escape helper
# ---------------------------------------------------------------------------


def _escape(s: str) -> str:
    """Escape for ReportLab Paragraph (XML-style; prevents injection in PDF content)."""
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# ---------------------------------------------------------------------------
#  Horizontal rule helper
# ---------------------------------------------------------------------------


def _hr():
    """Return a styled horizontal rule flowable."""
    return HRFlowable(width="100%", thickness=0.5, color=_HR_COLOR, spaceBefore=6, spaceAfter=6)


# ---------------------------------------------------------------------------
#  Build the metadata header block
# ---------------------------------------------------------------------------


def _build_header(case_id: str, meta: dict, styles: dict) -> list:
    """Build the title + metadata header flowables."""
    story = []

    # Title
    story.append(Paragraph(_escape(case_id), styles["title"]))
    story.append(Spacer(1, 4))

    # Keywords
    keywords = meta.get("keywords", [])
    if keywords:
        story.append(Paragraph(_escape("Asiasanat / Keywords"), styles["meta_label"]))
        for kw in keywords:
            story.append(Paragraph(_escape(kw), styles["meta_value"]))
        story.append(Spacer(1, 4))

    # Metadata key-value pairs
    meta_rows = [
        ("Tapausvuosi / Case year", meta.get("case_year")),
        ("Antopäivä / Date of issue", meta.get("decision_date")),
        ("Diaarinumero / Diary number", meta.get("diary_number")),
        ("Taltio / Volume", meta.get("volume")),
        ("ECLI", meta.get("ecli")),
    ]
    for label, value in meta_rows:
        if value:
            text = f"<b>{_escape(label)}:</b>  {_escape(value)}"
            story.append(Paragraph(text, styles["meta_value"]))

    story.append(Spacer(1, 2))
    story.append(_hr())

    return story


# ---------------------------------------------------------------------------
#  Main PDF generation
# ---------------------------------------------------------------------------


def _override_meta_from_doc(meta: dict, doc: CaseLawDocument) -> None:
    """Override parsed metadata with populated doc fields (from regex extractor / ingestion)."""
    field_map = {"ecli": "ecli", "decision_date": "decision_date", "diary_number": "diary_number", "volume": "volume"}
    for doc_attr, meta_key in field_map.items():
        value = getattr(doc, doc_attr, None)
        if value:
            meta[meta_key] = value
    if getattr(doc, "legal_domains", None):
        meta["keywords"] = doc.legal_domains


def _render_body(body_lines: list[str], styles: dict, story: list) -> None:
    """Classify and render body lines into styled PDF flowables."""
    current_block: list[str] = []
    current_type = "body"
    seen_judge = False

    def flush():
        if not current_block:
            return
        joined = " ".join(current_block)
        if joined.strip():
            story.append(Paragraph(_escape(joined), styles.get(current_type, styles["body"])))

    for line in body_lines:
        stripped = line.strip()
        line_type = _classify_line(stripped)

        if line_type == "blank":
            flush()
            current_block, current_type = [], "body"
            continue

        # Standalone types: flush current block, render immediately
        if line_type in ("section_heading", "sub_heading"):
            flush()
            current_block = []
            label = stripped.upper() if line_type == "section_heading" else stripped
            story.append(Paragraph(_escape(label), styles[line_type]))
            current_type = "body"
            continue

        if line_type == "judge_line":
            flush()
            current_block = []
            if not seen_judge:
                story.append(_hr())
                seen_judge = True
            story.append(Paragraph(_escape(stripped), styles["judge_line"]))
            current_type = "body"
            continue

        if line_type == "law_ref":
            flush()
            current_block = []
            story.append(Paragraph(_escape(stripped), styles["law_ref"]))
            current_type = "body"
            continue

        # Numbered: each new number starts a fresh block
        if line_type == "numbered":
            flush()
            current_block, current_type = [stripped], "numbered"
            continue

        # Body text: accumulate (may continue a numbered paragraph)
        if current_type == "numbered" and not _NUMBERED.match(stripped):
            current_block.append(stripped)
        else:
            if current_type != "body":
                flush()
                current_block, current_type = [], "body"
            current_block.append(stripped)

    flush()


def doc_to_pdf(doc: CaseLawDocument | None) -> bytes:
    """
    Convert a CaseLawDocument to a professionally formatted PDF that mirrors
    the Finlex website layout. Supports Finnish (ä, ö, Å).
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

    styles = _build_styles()
    meta = _parse_metadata_from_text(text)
    _override_meta_from_doc(meta, doc)

    doc_template = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    story: list = []
    story.extend(_build_header(case_id, meta, styles))

    body_lines = _get_body_lines(text, meta.get("body_start", 0))
    _render_body(body_lines, styles, story)

    url = getattr(doc, "url", "") or ""
    if url:
        story.append(Spacer(1, 10))
        story.append(Paragraph(f"Source: {_escape(url)}", styles["footer_note"]))

    doc_template.build(story)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
#  File utilities (unchanged interface)
# ---------------------------------------------------------------------------


def _sanitize_filename(case_id: str | None) -> str:
    """Sanitize case_id for use as filename (e.g. KKO:2025:1 -> KKO-2025-1.pdf)."""
    if not (case_id or "").strip():
        return "unknown"
    return re.sub(r"[^\w\-.]", "-", (case_id or "").strip()).strip("-") or "case"


def write_pdf_for_document(doc: CaseLawDocument | None, output_path: str | Path) -> Path:
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


def get_pdf_filename(case_id: str | None) -> str:
    """Return the PDF filename for a case_id (e.g. KKO-2025-1.pdf). Handles None/empty."""
    return _sanitize_filename(case_id) + ".pdf"
