"""
© 2026 Crest Advisory Group LLC. All rights reserved.

PROPRIETARY AND CONFIDENTIAL

This file is part of the Crest Pet System and contains proprietary
and confidential information of Crest Advisory Group LLC.
Unauthorized copying, distribution, or use is strictly prohibited.
"""

"""
Case Law Domain Models

Pure data structures with no external dependencies. Extracted from scraper.py
so that modules which only need the data models (e.g. protocols, storage)
don't transitively pull in bs4 / playwright.
"""

from dataclasses import asdict, dataclass, field


@dataclass
class Reference:
    """Represents a reference to another legal document"""

    ref_id: str  # e.g., 'KKO:2020:15' or 'RL 46:1'
    ref_type: str  # 'precedent', 'legislation'


@dataclass
class CaseLawDocument:
    """Represents a scraped case law document"""

    # Required Fields (No Defaults)
    case_id: str  # e.g., "KKO:2026:1" or "KHO 22.1.2026/149"
    court_type: str  # "supreme_court", "supreme_administrative_court"
    court_code: str  # "KKO", "KHO"
    decision_type: str  # "precedent", "other_decision"
    case_year: int

    # Optional Fields (With Defaults)
    decision_date: str | None = None  # ISO format YYYY-MM-DD
    diary_number: str | None = None
    ecli: str | None = None
    title: str = ""
    full_text: str = ""
    url: str = ""

    # Phase 3 Metadata
    primary_language: str = "Finnish"
    available_languages: list[str] = field(default_factory=lambda: ["Finnish"])

    # Parties
    applicant: str = ""
    defendant: str = ""
    respondent: str = ""

    # Lower Court
    lower_court_name: str = ""
    lower_court_date: str | None = None
    lower_court_number: str = ""
    lower_court_decision: str = ""

    # Appeal Court
    appeal_court_name: str = ""
    appeal_court_date: str | None = None
    appeal_court_number: str = ""

    # Metadata
    volume: str | None = None
    cited_regulations: list[str] = field(default_factory=list)  # e.g. "Council Regulation (EU) No 833/2014"

    # Decisions & Content
    background_summary: str = ""
    complaint: str = ""
    answer: str = ""
    decision_outcome: str = ""
    judgment: str = ""
    dissenting_opinion: bool = False
    dissenting_text: str = ""

    # Citations (Categorized)
    legal_domains: list[str] = field(default_factory=list)
    cited_laws: list[str] = field(default_factory=list)
    cited_cases: list[str] = field(default_factory=list)
    cited_government_proposals: list[str] = field(default_factory=list)
    cited_eu_cases: list[str] = field(default_factory=list)

    # Legacy & Utils
    references: list[Reference] = field(default_factory=list)
    collective_agreements: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    # Metadata
    is_precedent: bool = False

    # Content sections
    abstract: str = ""
    judges: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
