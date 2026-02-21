"""
Shared test helpers. Used across unit tests to avoid duplication.
"""

from src.services.case_law.models import CaseLawDocument


def make_case_law_doc(**overrides: object) -> CaseLawDocument:
    """Create a minimal CaseLawDocument with sensible defaults for tests."""
    defaults: dict[str, object] = {
        "case_id": "KKO:2024:1",
        "court_type": "supreme_court",
        "court_code": "KKO",
        "decision_type": "precedent",
        "case_year": 2024,
        "title": "Test Case",
        "full_text": "Some legal text content.",
    }
    defaults.update(overrides)
    return CaseLawDocument(**defaults)


def make_search_chunk(
    chunk_id: str,
    text: str = "",
    case_id: str = "",
    score: float = 0.5,
) -> dict:
    """Create a minimal search-result chunk dict for retrieval tests."""
    return {
        "id": chunk_id,
        "text": text,
        "source": "case_law",
        "metadata": {"case_id": case_id},
        "score": score,
    }
