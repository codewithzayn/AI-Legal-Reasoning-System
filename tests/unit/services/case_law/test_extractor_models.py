"""
Unit tests for case law extractor models (src.services.case_law.extractor).
"""

from src.services.case_law.extractor import (
    CaseExtractionResult,
    CaseMetadata,
    CaseSection,
    LowerCourts,
    References,
)


def test_case_section_has_required_fields():
    """CaseSection has type, title, content."""
    section = CaseSection(type="reasoning", title="Perustelut", content="Some text.")
    assert section.type == "reasoning"
    assert section.title == "Perustelut"
    assert section.content == "Some text."


def test_case_extraction_result_requires_metadata_sections():
    """CaseExtractionResult is valid with metadata, lower_courts, references, sections."""
    metadata = CaseMetadata(
        case_id="KKO:2024:1",
        ecli="ECLI:FI:KKO:2024:1",
        date_of_issue="2024-01-15",
        diary_number="R1/2024",
        decision_outcome="appeal_dismissed",
        judges=["Judge A"],
        rapporteur="Rapporteur B",
        keywords=[],
        languages=["Finnish"],
    )
    lower_courts = LowerCourts(district_court=None, appeal_court=None)
    references = References(
        cited_cases=[],
        cited_eu_cases=[],
        cited_laws=[],
        cited_regulations=[],
    )
    sections = [
        CaseSection(type="reasoning", title="Reasoning", content="Reasoning text."),
        CaseSection(type="judgment", title="Judgment", content="Judgment text."),
    ]
    result = CaseExtractionResult(
        metadata=metadata,
        lower_courts=lower_courts,
        references=references,
        sections=sections,
    )
    assert result.metadata.case_id == "KKO:2024:1"
    assert len(result.sections) == 2
    assert result.sections[0].type == "reasoning"
    assert result.sections[1].type == "judgment"
