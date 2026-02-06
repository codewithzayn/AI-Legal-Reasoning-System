# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL. Unauthorized copying, distribution, or use is strictly prohibited.

"""
Hybrid precedent extractor: regex first, LLM fallback (GPT-4o mini).
Ensures no empty sections and no missing chunks; returns CaseExtractionResult.
"""

import json
import os

from openai import OpenAI

from src.config.logging_config import setup_logger
from src.services.case_law.extractor import (
    CaseExtractionResult,
    CaseMetadata,
    CaseSection,
    LowerCourts,
    References,
)
from src.services.case_law.regex_extractor import extract_precedent

logger = setup_logger(__name__)

COVERAGE_THRESHOLD = 0.90
EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL", "gpt-4o-mini")
MAX_TEXT_FOR_LLM = 120_000

VALID_SECTION_TYPES = (
    "lower_court",
    "appeal_court",
    "background",
    "reasoning",
    "judgment",
    "other",
)

LLM_SYSTEM_PROMPT = """You extract sections from a Finnish Supreme Court (KKO) precedent text.
Output a JSON array of section objects. Each object must have:
- "type": one of lower_court, appeal_court, background, reasoning, judgment, other
- "title": short section title (e.g. "Reasoning", "Perustelut")
- "content": full text of that section (no truncation)

Split the document by standard headings (e.g. Asian käsittely alemmissa oikeuksissa, Perustelut, Tuomiolauselma).
Include every part of the document in exactly one section. Output only the JSON array, no markdown or explanation."""

LLM_USER_PROMPT_TEMPLATE = """Extract sections from this KKO precedent (case_id: {case_id}). Output only a JSON array of objects with keys type, title, content.

Document:
{text}"""


def _is_sufficient(result: CaseExtractionResult, full_text: str) -> bool:
    """True if regex result has enough sections and coverage."""
    if not result.sections:
        return False
    total_content_len = sum(len(s.content or "") for s in result.sections)
    text_len = len(full_text.strip()) or 1
    if total_content_len < COVERAGE_THRESHOLD * text_len:
        return False
    return all(s.content and s.content.strip() for s in result.sections)


def _normalize_sections(sections: list[CaseSection], full_text: str) -> list[CaseSection]:
    """Drop empty content; if no sections left, add one from full_text."""
    out: list[CaseSection] = []
    for s in sections:
        if not s.content or not s.content.strip():
            continue
        sec_type = (s.type or "").strip() or "other"
        if sec_type not in VALID_SECTION_TYPES:
            sec_type = "other"
        out.append(
            CaseSection(
                type=sec_type,
                title=(s.title or "").strip() or "Section",
                content=s.content.strip(),
            )
        )
    if not out and full_text.strip():
        out = [
            CaseSection(
                type="other",
                title="Full text",
                content=full_text.strip()[:MAX_TEXT_FOR_LLM],
            )
        ]
    return out


def _minimal_metadata(case_id: str) -> CaseMetadata:
    """Build minimal metadata when regex returns nothing."""
    parts = case_id.replace(" ", ":").split(":")
    year = parts[1] if len(parts) >= 2 else "0000"
    return CaseMetadata(
        case_id=case_id,
        ecli=f"ECLI:FI:KKO:{year}:{parts[-1] if len(parts) >= 3 else '0'}",
        date_of_issue=f"{year}-01-01",
        diary_number="",
        volume=None,
        decision_outcome="unknown",
        judges=["Unknown"],
        rapporteur="Unknown",
        keywords=[],
        languages=["Finnish", "Swedish"],
    )


def _minimal_lower_courts() -> LowerCourts:
    return LowerCourts(district_court=None, appeal_court=None)


def _minimal_references() -> References:
    return References(
        cited_cases=[],
        cited_eu_cases=[],
        cited_laws=[],
        cited_regulations=[],
    )


def _call_llm_for_sections(full_text: str, case_id: str) -> list[CaseSection]:
    """Call GPT-4o mini to extract sections; return list of CaseSection."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("%s | LLM fallback skipped (no OPENAI_API_KEY)", case_id)
        return []

    text = full_text.strip()
    if len(text) > MAX_TEXT_FOR_LLM:
        text = text[:MAX_TEXT_FOR_LLM] + "\n\n[Document truncated for extraction.]"

    client = OpenAI(api_key=api_key)
    user_content = LLM_USER_PROMPT_TEMPLATE.format(case_id=case_id, text=text)

    try:
        response = client.chat.completions.create(
            model=EXTRACTION_MODEL,
            messages=[
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
        )
        raw = response.choices[0].message.content or ""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1] if "\n" in raw else raw
            raw = raw.replace("```json", "").replace("```", "").strip()
        arr = json.loads(raw)
        sections: list[CaseSection] = []
        for item in arr if isinstance(arr, list) else []:
            if not isinstance(item, dict):
                continue
            sec_type = (item.get("type") or "other").strip() or "other"
            if sec_type not in VALID_SECTION_TYPES:
                sec_type = "other"
            title = (item.get("title") or "").strip() or "Section"
            content = (item.get("content") or "").strip()
            if content:
                sections.append(CaseSection(type=sec_type, title=title, content=content))
        return sections
    except json.JSONDecodeError as e:
        logger.warning("%s | LLM invalid JSON: %s", case_id, e)
        return []
    except Exception as e:
        logger.exception("%s | LLM extraction failed: %s", case_id, e)
        return []


def extract_precedent_hybrid(full_text: str, case_id: str) -> CaseExtractionResult | None:
    """
    Extract structured data: regex first, LLM fallback if coverage insufficient.
    Never returns empty sections; normalizes to avoid nulls.
    """
    if not full_text or not full_text.strip():
        logger.warning("%s | skip (empty full_text)", case_id)
        return None

    text = full_text.strip()
    if not case_id:
        case_id = "KKO:0000:0"

    regex_result = extract_precedent(full_text, case_id)

    if regex_result and _is_sufficient(regex_result, text):
        sections = _normalize_sections(regex_result.sections, text)
        logger.info("%s | regex sufficient (%s sections)", case_id, len(sections))
        return CaseExtractionResult(
            metadata=regex_result.metadata,
            lower_courts=regex_result.lower_courts,
            references=regex_result.references,
            sections=sections,
        )

    if regex_result:
        metadata = regex_result.metadata
        lower_courts = regex_result.lower_courts
        references = regex_result.references
    else:
        metadata = _minimal_metadata(case_id)
        lower_courts = _minimal_lower_courts()
        references = _minimal_references()

    logger.info("%s | LLM fallback (regex insufficient)", case_id)
    llm_sections = _call_llm_for_sections(full_text, case_id)
    sections = _normalize_sections(llm_sections, text)
    logger.info("%s | LLM fallback done (%s sections)", case_id, len(sections))

    return CaseExtractionResult(
        metadata=metadata,
        lower_courts=lower_courts,
        references=references,
        sections=sections,
    )


class HybridPrecedentExtractor:
    """
    Hybrid extractor for Supreme Court precedents: regex first, GPT-4o mini fallback.
    Use extract_data(full_text, case_id) to get a CaseExtractionResult.
    """

    def extract_data(self, full_text: str, case_id: str) -> CaseExtractionResult | None:
        return extract_precedent_hybrid(full_text, case_id)
