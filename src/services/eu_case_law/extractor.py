"""
EU Case Law Section Extractor

Splits CJEU and ECHR judgment full-text into typed sections using regex
patterns for section markers in English and Finnish. Falls back to chunked
full text when no markers are found.
"""

import re

from src.config.logging_config import setup_logger

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# CJEU section markers (English + Finnish variants)
# ---------------------------------------------------------------------------
_CJEU_SECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "legal_framework",
        re.compile(
            r"^(?:Legal\s+framework|I\s*[\u2013\u2014\u2015-]\s*Legal\s+framework|"
            r"Oikeudellinen\s+kehys|Asiaa\s+koskevat\s+oikeuss\u00e4\u00e4nn\u00f6t)",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "background",
        re.compile(
            r"^(?:Background\s+to\s+the\s+(?:dispute|main\s+proceedings)|"
            r"The\s+(?:dispute\s+in|main\s+proceedings)|"
            r"P\u00e4\u00e4asian\s+oikeusriita|Tosiseikat)",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "preliminary_question",
        re.compile(
            r"^(?:The\s+questions?\s+referred|Questions?\s+referred\s+for\s+a\s+preliminary\s+ruling|"
            r"Ennakkoratkaisukysymy)",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "reasoning",
        re.compile(
            r"^(?:Findings?\s+of\s+the\s+Court|Consideration\s+of\s+the\s+questions?\s+referred|"
            r"Unionin\s+tuomioistuimen\s+arviointi|Ennakkoratkaisukysymysten\s+tarkastelu)",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "costs",
        re.compile(
            r"^(?:Costs|Oikeudenk\u00e4yntikulut)",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "operative_part",
        re.compile(
            r"^(?:On\s+those\s+grounds|Operative\s+part|"
            r"N\u00e4ill\u00e4\s+perusteilla|Tuomiolauselma)",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "advocate_general_opinion",
        re.compile(
            r"^(?:Opinion\s+of\s+Advocate\s+General|"
            r"Julkisasiamiehen\s+ratkaisuehdotus)",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
]

# ---------------------------------------------------------------------------
# ECHR section markers
# ---------------------------------------------------------------------------
_ECHR_SECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "facts",
        re.compile(
            r"^(?:THE\s+FACTS|I\.\s*THE\s+FACTS|PROCEDURE)",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "findings_of_fact",
        re.compile(
            r"^(?:THE\s+CIRCUMSTANCES\s+OF\s+THE\s+CASE|"
            r"II\.\s*THE\s+CIRCUMSTANCES)",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "legal_framework",
        re.compile(
            r"^(?:RELEVANT\s+(?:DOMESTIC\s+)?LAW|"
            r"III\.\s*RELEVANT\s+(?:DOMESTIC\s+)?LAW)",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "law",
        re.compile(
            r"^(?:THE\s+LAW|II\.\s*THE\s+LAW)",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "operative_part",
        re.compile(
            r"^(?:FOR\s+THESE\s+REASONS|OPERATIVE\s+PROVISIONS)",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "concurring_opinion",
        re.compile(
            r"^(?:CONCURRING\s+OPINION|JOINT\s+CONCURRING\s+OPINION)",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "separate_opinion",
        re.compile(
            r"^(?:(?:PARTLY\s+)?DISSENTING\s+OPINION|SEPARATE\s+OPINION|"
            r"JOINT\s+(?:PARTLY\s+)?DISSENTING\s+OPINION)",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
]


class EUCaseExtractor:
    """Extract sections from EU case law full text."""

    @staticmethod
    def extract_cjeu(full_text: str, case_id: str, language: str = "EN") -> list[dict]:
        """Extract sections from a CJEU/General Court judgment.

        Args:
            full_text: The full judgment text.
            case_id: Case identifier for logging.
            language: 'EN' or 'FI' (affects marker variants).

        Returns:
            List of dicts: {"type": str, "title": str, "content": str}
        """
        return _extract_sections(full_text, case_id, _CJEU_SECTION_PATTERNS)

    @staticmethod
    def extract_echr(full_text: str, case_id: str) -> list[dict]:
        """Extract sections from an ECHR judgment.

        Args:
            full_text: The full judgment text.
            case_id: Case identifier for logging.

        Returns:
            List of dicts: {"type": str, "title": str, "content": str}
        """
        return _extract_sections(full_text, case_id, _ECHR_SECTION_PATTERNS)


def _extract_sections(
    full_text: str,
    case_id: str,
    patterns: list[tuple[str, re.Pattern]],
) -> list[dict]:
    """Generic section extractor: find section markers and split text.

    Falls back to a single 'reasoning' section when no markers are found.
    """
    if not full_text or not full_text.strip():
        return []

    # Find all marker positions
    markers: list[tuple[int, str, str]] = []  # (position, section_type, matched_text)
    for sec_type, pattern in patterns:
        for m in pattern.finditer(full_text):
            markers.append((m.start(), sec_type, m.group(0).strip()))

    if not markers:
        logger.info("%s | no section markers found, using full text as single section", case_id)
        return [{"type": "reasoning", "title": "Full Text", "content": full_text.strip()}]

    # Sort by position
    markers.sort(key=lambda x: x[0])

    sections: list[dict] = []

    # Text before first marker → 'background'
    if markers[0][0] > 100:
        preamble = full_text[: markers[0][0]].strip()
        if preamble:
            sections.append({"type": "background", "title": "Preamble", "content": preamble})

    # Extract each section
    for i, (pos, sec_type, title) in enumerate(markers):
        end = markers[i + 1][0] if i + 1 < len(markers) else len(full_text)
        content = full_text[pos:end].strip()
        # Strip the marker line from content
        first_newline = content.find("\n")
        if first_newline > 0:
            content = content[first_newline:].strip()
        if content:
            sections.append({"type": sec_type, "title": title, "content": content})

    logger.info("%s | extracted %s sections", case_id, len(sections))
    return sections
