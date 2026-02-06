# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL. Unauthorized copying, distribution, or use is strictly prohibited.

"""
Case law extraction models.
Shared Pydantic schemas used by the regex extractor and GPT-4o mini LLM fallback (hybrid_extractor).
"""

from pydantic import BaseModel, Field


class CourtDecision(BaseModel):
    name: str = Field(description="Name of the court (e.g., Kymenlaakson käräjäoikeus)")
    date: str = Field(description="Decision date in YYYY-MM-DD format")
    number: str = Field(description="Court case number (e.g., 23/116279)")
    content_summary: str = Field(description="Brief summary of what this court decided")


class LowerCourts(BaseModel):
    district_court: CourtDecision | None = Field(description="First instance court info")
    appeal_court: CourtDecision | None = Field(description="Appeal court info")


class CitedRegulation(BaseModel):
    name: str = Field(description="Name of regulation (e.g., Council Regulation (EU) No 833/2014)")
    article: str | None = Field(description="Specific article cited (e.g., Article 5i)")


class References(BaseModel):
    cited_cases: list[str] = Field(description="List of cited Finnish cases (e.g., KKO 2018:49)")
    cited_eu_cases: list[str] = Field(description="List of cited EU cases (e.g., C-246/24)")
    cited_laws: list[str] = Field(description="List of cited national laws (e.g., RL 46:1)")
    cited_regulations: list[CitedRegulation] = Field(description="EU Regulations or Treaties cited")


class CaseMetadata(BaseModel):
    case_id: str = Field(description="The KKO ID (e.g. KKO:2026:1)")
    ecli: str = Field(description="ECLI code (e.g., ECLI:FI:KKO:2026:1)")
    date_of_issue: str = Field(description="Date of issue in YYYY-MM-DD")
    diary_number: str = Field(description="Diary number (e.g., R2024/357)")
    volume: str | None = Field(description="Volume number if applicable")

    decision_outcome: str = Field(description="Outcome: appeal_dismissed, appeal_accepted, case_remanded, etc.")
    judges: list[str] = Field(description="List of names of the judges who decided the case")
    rapporteur: str = Field(description="Name of the legal rapporteur")

    keywords: list[str] = Field(description="List of legal keywords describing the case")
    languages: list[str] = Field(description="Languages available (e.g. ['Finnish', 'Swedish'])")


class CaseSection(BaseModel):
    type: str = Field(description="Type: lower_court, appeal_court, background, reasoning, judgment")
    title: str = Field(description="Title of the section")
    content: str = Field(description="Full text content of the section")


class CaseExtractionResult(BaseModel):
    metadata: CaseMetadata
    lower_courts: LowerCourts
    references: References
    sections: list[CaseSection]
