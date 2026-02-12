# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL. Unauthorized copying, distribution, or use is strictly prohibited.

"""
Regex-based extractor for Finnish Supreme Court (KKO) precedents.
Populates the same CaseExtractionResult as the LLM extractor for cost-effective ingestion.
"""

import re

from src.config.logging_config import setup_logger
from src.services.case_law.extractor import (
    CaseExtractionResult,
    CaseMetadata,
    CaseSection,
    CitedRegulation,
    CourtDecision,
    LowerCourts,
    References,
)

logger = setup_logger(__name__)

# --- KKO Precedent patterns (English/Finnish header block) ---
PATTERN_CASE_ID = re.compile(r"KKO\s*:\s*(\d{4})\s*:\s*(\d+)", re.IGNORECASE)
PATTERN_ECLI = re.compile(r"ECLI\s*:\s*FI\s*:\s*KKO\s*:\s*(\d{4})\s*:\s*(\d+)", re.IGNORECASE)
PATTERN_DIARY_NUMBER = re.compile(
    r"(?:Diary number|Päiväkirjanumero|Dnro)\s*\n\s*([A-Z]?\s*\d{4}/\d+(?:\s*\d+)?|[A-Z]?\s*\d+/\d{4}/\d+|S\d{4}/\d+|\d+:\d{4})",
    re.IGNORECASE | re.MULTILINE,
)
PATTERN_VOLUME = re.compile(
    r"(?:Volume|Taltio)\s*\n\s*([^\n]+?)(?=\s*\n|$)",
    re.IGNORECASE | re.MULTILINE,
)
# Date: "January 7, 2026" or "18.12.2024" or "13.12.2019"
PATTERN_DATE_EN = re.compile(
    r"(?:Date of issue|Antopäivä)\s*\n\s*((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})",
    re.IGNORECASE | re.MULTILINE,
)
PATTERN_DATE_DMYY = re.compile(
    r"(?:Date of issue|Antopäivä)\s*\n\s*(\d{1,2})\.(\d{1,2})\.(\d{4})",
    re.IGNORECASE | re.MULTILINE,
)
PATTERN_CASE_YEAR = re.compile(
    r"(?:Case year|Kausi)\s*\n\s*(\d{4})",
    re.IGNORECASE | re.MULTILINE,
)

# Keywords: lines after "Keywords" until next known key (Case year, Date of issue, etc.)
KEYWORDS_START = re.compile(r"^\s*Keywords\s*$", re.IGNORECASE | re.MULTILINE)
KEYWORDS_END = re.compile(
    r"^\s*(?:Case year|Date of issue|Language versions|Kausi|Antopäivä|Päiväkirjanumero)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Section headers (order matters for splitting). Covers 1926–2026 KKO formats (Finnish/English, various phrasings).
SECTION_HEADERS = [
    (
        "lower_court",
        re.compile(
            r"^(?:Hearing of the case in lower courts|Asian käsittely alemmissa oikeuksissa|Previous handling of the case|Asian käsittely)\s*$",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "appeal_section",
        re.compile(
            r"^(?:Appeal to the Supreme Court|Muutoksenhaku Korkeimmassa oikeudessa|Additional appeal to the Supreme Court)\s*$",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "supreme_decision",
        re.compile(r"^(?:Supreme Court decision|Korkeimman oikeuden ratkaisu)\s*$", re.IGNORECASE | re.MULTILINE),
    ),
    (
        "reasoning",
        re.compile(
            r"^(?:Reasoning|Perustelut|Pääasiaratkaisun perustelut|Korkeimman oikeuden kannanotot|Johtopäätös)\s*$",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "background",
        re.compile(
            r"^(?:Background of the matter|Asian tausta|Asian tausta ja kysymyksenasettelu)\s*$",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "legislation",
        re.compile(
            r"^(?:Legislation|Lainsäädäntö|Sovellettava (?:lainsäädäntö|säännös)|Applicable (?:law|provision))\s*$",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "question",
        re.compile(
            r"^(?:Question(?:ing)? (?:in the Supreme Court|before the court)?|Kysymyksenasettelu (?:Korkeimmassa oikeudessa)?)\s*$",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "judgment",
        re.compile(
            r"^(?:Judgment|Tuomiolauselma|Päätöslauselma|Päätös)\s*$",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "dissenting",
        re.compile(
            r"^(?:Statement of (?:a )?dissenting member|Eri mieltä olevan jäsenen lausunto|Eri mieltä olevien jäsenten lausunnot)\s*$",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
]
# Judges line at end
PATTERN_JUDGES_LINE = re.compile(
    r"(?:The case has been resolved|The matter has been resolved|Asian on käsitellyt)\s+[Bb]y\s+(.+?)\s*\.\s*Rapporteur\s+([A-Za-zäöåÄÖÅ\- ]+)\s*\.?\s*$",
    re.IGNORECASE | re.DOTALL,
)
PATTERN_JUDGES_LINE_ALT = re.compile(
    r"Rapporteur\s+([A-Za-zäöåÄÖÅ\- ]+)\s*\.?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Lower court: e.g. "Kymenlaakso District Court judgment 20.4.2023 no. 23/116279" or "District Court judgment of 18 October 2021 no. 21/48930"
PATTERN_DISTRICT_COURT = re.compile(
    r"(?:([^\n]+?)\s+)?(?:District Court|Käräjäoikeus)\s+(?:judgment|tuomio)\s+(?:of\s+)?(\d{1,2}[./]\d{1,2}[./]\d{2,4})\s+(?:no\.?|n:o)\s*(\d{2}/\d+)",
    re.IGNORECASE,
)
PATTERN_APPEAL_COURT = re.compile(
    r"(?:([^\n]+?)\s+)?(?:Court of Appeal|Hovioikeus)\s+(?:judgment|tuomio)?\s*,?\s*(\d{1,2}\s+\w+\s+\d{4}|\d{1,2}[./]\d{1,2}[./]\d{2,4})\s*,?\s*(?:no\.?|n:o)?\s*(\d{2}/\d+|\d+)",
    re.IGNORECASE,
)

# Citations in body
PATTERN_KKO_CITE = re.compile(r"KKO\s+(\d{4})\s*:\s*(\d+)", re.IGNORECASE)
PATTERN_EU_CASE = re.compile(r"(?:CJEU|ECJ|Court of Justice).*?(C-\d+/\d+)", re.IGNORECASE)
PATTERN_EU_CASE_BARE = re.compile(r"\b(C-\d+/\d+)\b")
PATTERN_RL = re.compile(
    r"(?:RL|Rikoslaki)\s+(?:Chapter\s+)?(\d+)\s*(?:Section\s+)?(\d+)(?:\s*Subsection\s*\d+)?(?:\s*Paragraph\s*\d+)?(?:\s*\(\d+/\d+\))?",
    re.IGNORECASE,
)
PATTERN_LAW_CHAPTER = re.compile(r"(?:Chapter|Luku)\s+(\d+)\s*,?\s*(?:Section|§)\s*(\d+[a-z]?)", re.IGNORECASE)
PATTERN_EU_REGULATION = re.compile(
    r"(Council\s+Regulation\s+\(EU\)\s+No\s+\d+/\d+(?:\s+[^.]*?)?)(?:\s*[,.]|$)|(Regulation\s+\(EU\)\s+\d+/\d+)",
    re.IGNORECASE,
)
PATTERN_EU_REGULATION_ARTICLE = re.compile(
    r"Article\s+(\d+[a-z]?)(?:\((\d+)\))?\s*(?:of\s+the\s+)?(?:Regulation|Council Regulation)",
    re.IGNORECASE,
)

MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _normalize_date_en(match: re.Match) -> str:
    raw = match.group(1).strip()
    parts = re.split(r"[\s,]+", raw, maxsplit=2)
    if len(parts) >= 3:
        month_name, day, year = parts[0], parts[1], parts[2]
        month = MONTH_NAMES.get(month_name.lower(), 1)
        try:
            d = int(day.strip(","))
            y = int(year)
            return f"{y}-{month:02d}-{d:02d}"
        except ValueError:
            pass
    return ""


def _normalize_date_dmyy(match: re.Match) -> str:
    d, m, y = match.group(1), match.group(2), match.group(3)
    try:
        return f"{int(y)}-{int(m):02d}-{int(d):02d}"
    except ValueError:
        return ""


def _extract_keywords(text: str) -> list[str]:
    start = KEYWORDS_START.search(text)
    if not start:
        return []
    pos = start.end()
    end = KEYWORDS_END.search(text[pos:])
    block = text[pos : pos + end.start()] if end else text[pos : pos + 800]
    lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
    return lines[:50]


def _extract_judges(text: str) -> tuple[list[str], str]:
    """Extract judges list and rapporteur name from text. Returns (judges, rapporteur)."""
    judges: list[str] = []
    rapporteur = ""
    judges_m = PATTERN_JUDGES_LINE.search(text)
    if judges_m:
        judge_block = judges_m.group(1)
        rapporteur = judges_m.group(2).strip()
        for part in re.split(r"\s+and\s+|\s*,\s*", judge_block):
            name = part.replace("legal advisors", "").replace("Legal Counselors", "").replace("President", "").strip()
            if name and len(name) > 2:
                judges.append(name)
    if not rapporteur:
        rapp_m = PATTERN_JUDGES_LINE_ALT.search(text[-2000:])
        if rapp_m:
            rapporteur = rapp_m.group(1).strip()
    return judges, rapporteur


# Optional: date with 2-digit year (e.g. "1.1.59", "18.12.24") for older documents
PATTERN_DATE_DMYY_2DIGIT = re.compile(
    r"(?:Date of issue|Antopäivä)\s*\n\s*(\d{1,2})\.(\d{1,2})\.(\d{2})\b",
    re.IGNORECASE | re.MULTILINE,
)


def _two_digit_year_to_four(yy: str) -> str:
    """Convert 2-digit year to 4-digit: 00-30 -> 2000-2030, 31-99 -> 1931-1999."""
    n = int(yy)
    return str(2000 + n) if n <= 30 else str(1900 + n)


def _extract_date_of_issue(text: str, case_year: str) -> str:
    """Extract date of issue from header block. Returns ISO date string. Tries multiple formats."""
    header = text[:4000]
    date_m = PATTERN_DATE_EN.search(header)
    if date_m:
        result = _normalize_date_en(date_m)
        if result:
            return result
    date_dm = PATTERN_DATE_DMYY.search(header)
    if date_dm:
        result = _normalize_date_dmyy(date_dm)
        if result:
            return result
    date_dm2 = PATTERN_DATE_DMYY_2DIGIT.search(header)
    if date_dm2:
        yyyy = _two_digit_year_to_four(date_dm2.group(3))
        return f"{yyyy}-{int(date_dm2.group(2)):02d}-{int(date_dm2.group(1)):02d}"
    if case_year and str(case_year).strip() and re.match(r"^\d{4}$", str(case_year).strip()):
        return f"{case_year.strip()}-01-01"
    return ""


def _year_from_case_id(case_id: str) -> str:
    """Derive 4-digit year from case_id (e.g. KKO:1959:II-110 or KKO:1959-II-110 -> 1959). Empty if unparseable."""
    if not case_id:
        return ""
    parts = re.split(r"[:\-]", str(case_id).strip(), maxsplit=2)
    for p in parts[1:2] if len(parts) >= 2 else []:
        if re.match(r"^\d{4}$", p.strip()):
            return p.strip()
    return ""


def _extract_metadata_block(text: str, case_id: str) -> CaseMetadata:
    header = text[:4000]

    case_year_m = PATTERN_CASE_YEAR.search(header)
    case_year = case_year_m.group(1) if case_year_m else ""

    ecli_m = PATTERN_ECLI.search(header)
    ecli = f"ECLI:FI:KKO:{ecli_m.group(1)}:{ecli_m.group(2)}" if ecli_m else ""

    dn_m = PATTERN_DIARY_NUMBER.search(header)
    diary_number = dn_m.group(1).strip() if dn_m else ""

    vol_m = PATTERN_VOLUME.search(header)
    volume = vol_m.group(1).strip() if vol_m else None

    date_of_issue = _extract_date_of_issue(text, case_year)
    keywords = _extract_keywords(text)
    judges, rapporteur = _extract_judges(text)

    decision_outcome = "appeal_dismissed"
    if re.search(r"appeal\s+(?:is\s+)?(?:accepted|granted)|muutoksenhaku\s+myönnetään", text, re.IGNORECASE):
        decision_outcome = "appeal_accepted"
    elif re.search(r"remanded|palautetaan", text, re.IGNORECASE):
        decision_outcome = "case_remanded"

    # Year: from header "Case year" or from case_id (e.g. KKO:1959:II-110) so we never emit invalid "-01-01"
    effective_year = (
        case_year.strip()
        if (case_year and re.match(r"^\d{4}$", str(case_year).strip()))
        else _year_from_case_id(case_id)
    )
    year_fallback = f"{effective_year}-01-01" if effective_year else ""
    return CaseMetadata(
        case_id=case_id,
        ecli=ecli or f"ECLI:FI:KKO:{case_id.split(':')[-2]}:{case_id.split(':')[-1]}" if ":" in case_id else "",
        date_of_issue=date_of_issue or year_fallback,
        diary_number=diary_number,
        volume=volume,
        decision_outcome=decision_outcome,
        judges=judges if judges else ["Unknown"],
        rapporteur=rapporteur or "Unknown",
        keywords=keywords,
        languages=["Finnish", "Swedish"],
    )


def _extract_lower_courts(text: str) -> LowerCourts:
    district_court: CourtDecision | None = None
    appeal_court: CourtDecision | None = None

    dc_m = PATTERN_DISTRICT_COURT.search(text)
    if dc_m:
        name = (dc_m.group(1) or "").strip() or "District Court"
        date_raw = dc_m.group(2)
        number = dc_m.group(3)
        district_court = CourtDecision(
            name=name,
            date=date_raw.replace(".", "-") if len(date_raw) <= 10 else date_raw,
            number=number,
            content_summary="",
        )

    ac_m = PATTERN_APPEAL_COURT.search(text)
    if ac_m:
        name = (ac_m.group(1) or "").strip() or "Court of Appeal"
        date_raw = ac_m.group(2) or ""
        number = (ac_m.group(3) or "").strip()
        appeal_court = CourtDecision(
            name=name,
            date=date_raw,
            number=number,
            content_summary="",
        )

    return LowerCourts(district_court=district_court, appeal_court=appeal_court)


def _extract_references(text: str) -> References:
    cited_cases: list[str] = []
    for m in PATTERN_KKO_CITE.finditer(text):
        cited_cases.append(f"KKO {m.group(1)}:{m.group(2)}")
    cited_cases = list(dict.fromkeys(cited_cases))

    cited_eu_cases: list[str] = []
    for m in PATTERN_EU_CASE_BARE.finditer(text):
        cited_eu_cases.append(m.group(1))
    for m in PATTERN_EU_CASE.finditer(text):
        cited_eu_cases.append(m.group(1))
    cited_eu_cases = list(dict.fromkeys(cited_eu_cases))

    cited_laws: list[str] = []
    for m in PATTERN_RL.finditer(text):
        cited_laws.append(f"RL Chapter {m.group(1)} Section {m.group(2)}")
    for m in PATTERN_LAW_CHAPTER.finditer(text):
        cited_laws.append(f"Chapter {m.group(1)} Section {m.group(2)}")
    cited_laws = list(dict.fromkeys(cited_laws))[:100]

    cited_regulations: list[CitedRegulation] = []
    for m in PATTERN_EU_REGULATION.finditer(text):
        name = (m.group(1) or m.group(2) or "").strip()
        if name and len(name) > 10:
            art_m = PATTERN_EU_REGULATION_ARTICLE.search(text[max(0, m.start() - 50) : m.end() + 100])
            article = None
            if art_m:
                article = f"Article {art_m.group(1)}"
            cited_regulations.append(CitedRegulation(name=name, article=article))
    cited_regulations = cited_regulations[:30]

    return References(
        cited_cases=cited_cases,
        cited_eu_cases=cited_eu_cases,
        cited_laws=cited_laws,
        cited_regulations=cited_regulations,
    )


def _split_sections(full_text: str) -> list[tuple[str, str, str]]:
    """Return list of (section_type, title, content)."""
    sections: list[tuple[str, str, str]] = []
    text = full_text
    for i, (sec_type, pattern) in enumerate(SECTION_HEADERS):
        m = pattern.search(text)
        if not m:
            continue
        start = m.start()
        title = m.group(0).strip()
        next_start = len(text)
        for _, next_pat in SECTION_HEADERS[i + 1 :]:
            next_m = next_pat.search(text[start + 1 :])
            if next_m:
                next_start = min(next_start, start + 1 + next_m.start())
        content = text[start + len(m.group(0)) : next_start].strip()
        if content:
            sections.append((sec_type, title, content))
    return sections


def _build_sections(full_text: str) -> list[CaseSection]:
    raw_sections = _split_sections(full_text)
    result: list[CaseSection] = []
    type_map = {
        "lower_court": "lower_court",
        "appeal_section": "appeal_court",
        "supreme_decision": "supreme_decision",
        "reasoning": "reasoning",
        "background": "background",
        "legislation": "legislation",
        "question": "question",
        "judgment": "judgment",
        "dissenting": "dissenting",
    }
    for sec_type, title, content in raw_sections:
        normalized_type = type_map.get(sec_type, "other")
        result.append(CaseSection(type=normalized_type, title=title, content=content))
    return result


def extract_precedent(full_text: str, case_id: str) -> CaseExtractionResult | None:
    """
    Extract structured data from KKO precedent full text using regex only.
    Returns the same CaseExtractionResult as the LLM extractor for drop-in use.
    """
    if not full_text or not full_text.strip():
        logger.warning("Empty full_text for %s", case_id)
        return None

    text = full_text.strip()
    if not case_id and "KKO" in text:
        case_m = PATTERN_CASE_ID.search(text[:500])
        if case_m:
            case_id = f"KKO:{case_m.group(1)}:{case_m.group(2)}"
    if not case_id:
        case_id = "KKO:0000:0"

    try:
        metadata = _extract_metadata_block(text, case_id)
        lower_courts = _extract_lower_courts(text)
        references = _extract_references(text)
        sections = _build_sections(text)

        if not sections:
            reasoning_start = re.search(
                r"\n\s*(?:Reasoning|Perustelut|Pääasiaratkaisun perustelut|Johtopäätös)\s*\n",
                text,
                re.IGNORECASE,
            )
            judgment_start = re.search(
                r"\n\s*(?:Judgment|Tuomiolauselma|Päätöslauselma|Päätös)\s*\n",
                text,
                re.IGNORECASE,
            )
            if reasoning_start and judgment_start:
                sections.append(
                    CaseSection(
                        type="reasoning",
                        title="Reasoning",
                        content=text[reasoning_start.end() : judgment_start.start()].strip(),
                    )
                )
                sections.append(
                    CaseSection(
                        type="judgment",
                        title="Judgment",
                        content=text[judgment_start.end() :].strip(),
                    )
                )
            else:
                sections.append(CaseSection(type="other", title="Full text", content=text[:50000]))

        return CaseExtractionResult(
            metadata=metadata,
            lower_courts=lower_courts,
            references=references,
            sections=sections,
        )
    except Exception as e:
        logger.exception("Regex extraction failed for %s: %s", case_id, e)
        return None


class PrecedentRegexExtractor:
    """
    Regex-based extractor for Supreme Court precedents.
    Use extract_data(full_text, case_id) to get a CaseExtractionResult.
    """

    def extract_data(self, full_text: str, case_id: str) -> CaseExtractionResult | None:
        return extract_precedent(full_text, case_id)
