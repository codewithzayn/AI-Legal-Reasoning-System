"""
Case Law Extractor
Uses LLM (GPT-4o) to extract structured metadata from raw case text
"""

import os
import re
import json
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from src.config.logging_config import setup_logger

logger = setup_logger(__name__)

# --- Pydantic Models for Structured Output ---

class CourtDecision(BaseModel):
    name: str = Field(description="Name of the court (e.g., Kymenlaakson käräjäoikeus)")
    date: str = Field(description="Decision date in YYYY-MM-DD format")
    number: str = Field(description="Court case number (e.g., 23/116279)")
    content_summary: str = Field(description="Brief summary of what this court decided")

class LowerCourts(BaseModel):
    district_court: Optional[CourtDecision] = Field(description="First instance court info")
    appeal_court: Optional[CourtDecision] = Field(description="Appeal court info")

class CitedRegulation(BaseModel):
    name: str = Field(description="Name of regulation (e.g., Council Regulation (EU) No 833/2014)")
    article: Optional[str] = Field(description="Specific article cited (e.g., Article 5i)")

class References(BaseModel):
    cited_cases: List[str] = Field(description="List of cited Finnish cases (e.g., KKO 2018:49)")
    cited_eu_cases: List[str] = Field(description="List of cited EU cases (e.g., C-246/24)")
    cited_laws: List[str] = Field(description="List of cited national laws (e.g., RL 46:1)")
    cited_regulations: List[CitedRegulation] = Field(description="EU Regulations or Treaties cited")

class CaseMetadata(BaseModel):
    case_id: str = Field(description="The KKO ID (e.g. KKO:2026:1)")
    ecli: str = Field(description="ECLI code (e.g., ECLI:FI:KKO:2026:1)")
    date_of_issue: str = Field(description="Date of issue in YYYY-MM-DD")
    diary_number: str = Field(description="Diary number (e.g., R2024/357)")
    volume: Optional[str] = Field(description="Volume number if applicable")
    
    decision_outcome: str = Field(description="Outcome: appeal_dismissed, appeal_accepted, case_remanded, etc.")
    judges: List[str] = Field(description="List of names of the judges who decided the case")
    rapporteur: str = Field(description="Name of the legal rapporteur")
    
    keywords: List[str] = Field(description="List of legal keywords describing the case (e.g. Regulation offense, Sanctions case)")
    languages: List[str] = Field(description="Languages available (e.g. ['Finnish', 'Swedish'])")

class CaseSection(BaseModel):
    type: str = Field(description="Type: lower_court, appeal_court, background, reasoning, judgment")
    title: str = Field(description="Title of the section")
    content: str = Field(description="Full text content of the section")

class CaseExtractionResult(BaseModel):
    metadata: CaseMetadata
    lower_courts: LowerCourts
    references: References
    sections: List[CaseSection]


# --- Extractor Service ---

class CaseLawExtractor:
    """
    Service to extract structured data from raw legal text using LLMs.
    """
    
    def __init__(self, model_name: str = "gpt-4o"):
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=0,  # Maximize determinism
            max_tokens=4096, # Ensure enough room for full reasoning
            api_key=os.getenv("OPENAI_API_KEY")
        )
        self.structured_llm = self.llm.with_structured_output(CaseExtractionResult)
        
    def extract_data(self, full_text: str, case_id: str) -> Optional[CaseExtractionResult]:
        """
        Extract structured data from the full text of a case.
        Handles chunking for extremely large documents if necessary.
        """
        logger.info(f"Extracting data for {case_id} using AI...")
        
        try:
            # For now, we assume most cases fit in context window (128k tokens is huge)
            # If text is massive (>50k chars), we might want to truncate purely for cost/speed, 
            # but modern models handle it well.
            
            prompt = self._create_prompt(full_text)
            
            # Helper to clean text if needed before sending
            clean_text = self._clean_text(full_text)
            
            messages = [
                SystemMessage(content="You are an expert Finnish legal data extractor. Extract accurate structured data from the provided court decision."),
                HumanMessage(content=f"Analyze this document and extract all fields:\n\n{clean_text}")
            ]
            
            result = self.structured_llm.invoke(messages)
            
            logger.info(f"Extraction successful for {case_id}: Found {len(result.references.cited_cases)} cases, {len(result.sections)} sections")
            return result
            
        except Exception as e:
            logger.error(f"AI Extraction failed for {case_id}: {e}")
            return None

    def _clean_text(self, text: str) -> str:
        """Simple cleanup to reduce token usage without losing info"""
        # Remove multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text

    def _create_prompt(self, text: str) -> str:
        return """
You are an expert legal data extraction assistant specialized in Finnish Supreme Court (KKO) decisions.
Your task is to analyze the provided court decision text and extract structured metadata, references, and content sections.

### EXTRACTION RULES:

1. **METADATA**:
   - **Case ID**: Extract KKO identifier (e.g., KKO:2026:1).
   - **ECLI**: Extract ECLI code (e.g., ECLI:FI:KKO:2026:1).
   - **Diary Number**: Extract diary number (e.g., R2024/357).
   - **Date**: Extract "Date of issue" or "Antopäivä" in YYYY-MM-DD. Handle English dates like "January 20, 2026" (convert to 2026-01-20). It MUST NOT be null.
   - **Volume**: Extract the "Volume" or "Taltio" number if present (e.g. "38").
   - **Keywords**: Extract the list of keywords dealing with the legal topic (usually at the start).
   - **Judges**: List all judges named at the end of the document.
   - **Rapporteur**: Name of the rapporteur (Esittelijä).

2. **REFERENCES**:
   - **National Laws**: Finnish laws like "RL 46:1" or "Rikoslaki".
   - **National Cases**: KKO precedents (e.g., KKO 2018:49).
   - **EU Cases**: CJEU cases (e.g., C-246/24).
   - **Regulations**: **CRITICAL** - Extract EU Regulations cited (e.g., "Council Regulation (EU) No 833/2014").

3. **SECTIONS**:
   Split the document into these logical types:
   - `background`: "Asian tausta", "Background".
   - `lower_court`: "Käräjäoikeuden ratkaisu", "District Court judgment".
   - `appeal_court`: "Hovioikeuden ratkaisu", "Court of Appeal judgment".
   - `reasoning`: "Perustelut", "Reasoning" (The main legal analysis). 
     **IMPORTANT**: Capture the FULL reasoning text. Supreme Court decisions usually have numbered paragraphs (1., 2., 3., ...). Include ALL of them. DO NOT SUMMARIZE.
   - `judgment`: "Tuomiolauselma", "Judgment" (The final verdict).

**CRITICAL RULE**: The `content` field for each section must contain the raw, detailed text from the original document. Do not truncate, do not summarize, and do not paraphrase. Every legal argument and paragraph belonging to a section MUST be included.
"""
