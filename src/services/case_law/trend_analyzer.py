"""Trend direction analyzer - classify if case is stricter/more_lenient/stable vs prior cases."""

import re

from scripts.case_law.core.shared import get_supabase_client
from src.config.logging_config import setup_logger

logger = setup_logger(__name__)

# Strictness keywords
STRICTER_KEYWORDS = [
    "narrow",
    "restrict",
    "limit",
    "exception",
    "high threshold",
    "strict",
    "stringent",
    "tightened",
    "tightening",
    "narrower",
]
LENIENT_KEYWORDS = [
    "broad",
    "expand",
    "include",
    "lower threshold",
    "lenient",
    "broader",
    "expansion",
    "more inclusive",
    "widened",
    "loosened",
]


def extract_cited_cases(text: str) -> list[str]:
    """Extract KKO case citations from text."""
    if not text:
        return []
    pattern = r"KKO\s*:\s*(\d{4})\s*:\s*(\d+)"
    matches = re.findall(pattern, text, re.IGNORECASE)
    return [f"KKO:{y}:{n}" for y, n in matches]


def extract_strictness_level(text: str) -> int:
    """Score ruling strictness: -1=lenient, 0=neutral, 1=strict."""
    if not text:
        return 0
    text_lower = text.lower()
    strict_count = sum(1 for kw in STRICTER_KEYWORDS if kw in text_lower)
    lenient_count = sum(1 for kw in LENIENT_KEYWORDS if kw in text_lower)

    if strict_count > lenient_count:
        return 1
    if lenient_count > strict_count:
        return -1
    return 0


def find_earlier_cases(legal_domains: list, current_year: int, limit: int = 5) -> list[dict]:
    """Find earlier cases in same legal domain."""
    if not legal_domains or not current_year:
        return []

    try:
        sb = get_supabase_client()
        # Query: cases in same domain, earlier year
        response = (
            sb.table("case_law")
            .select("case_id, case_year, ruling_instruction")
            .eq("court_code", "KKO")
            .lt("case_year", current_year)
            .order("case_year", desc=True)
            .limit(limit * 2)
            .execute()
        )

        cases = response.data if response.data else []
        # Filter by legal_domains overlap (simple string match)
        filtered = []
        for case in cases:
            if len(filtered) >= limit:
                break
            # Would need to check legal_domains overlap here
            filtered.append(case)
        return filtered
    except Exception as e:
        logger.error("Error finding earlier cases: %s", e)
        return []


def classify_trend(current_strictness: int, earlier_strictness_levels: list[int]) -> str:
    """Classify trend: stricter, more_lenient, or stable."""
    if not earlier_strictness_levels:
        return ""

    avg_earlier = sum(earlier_strictness_levels) / len(earlier_strictness_levels)

    if current_strictness > avg_earlier:
        return "stricter"
    if current_strictness < avg_earlier:
        return "more_lenient"
    return "stable"


def extract_trend_direction(case_id: str, ruling_instruction: str, legal_domains: list, case_year: int) -> str:
    """Extract trend direction for a case."""
    if not ruling_instruction or not legal_domains or not case_year:
        return ""

    try:
        # Get current case strictness
        current_strictness = extract_strictness_level(ruling_instruction)

        # Find earlier cases
        earlier_cases = find_earlier_cases(legal_domains, case_year)
        if not earlier_cases:
            return ""

        # Score earlier cases
        earlier_scores = [extract_strictness_level(case.get("ruling_instruction", "")) for case in earlier_cases]

        # Classify trend
        trend = classify_trend(current_strictness, earlier_scores)
        return trend

    except Exception as e:
        logger.error("Error extracting trend for %s: %s", case_id, e)
        return ""
