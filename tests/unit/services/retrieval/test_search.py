# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL. Unauthorized copying, distribution, or use is strictly prohibited.

"""
Unit tests for HybridRetrieval: RRF merge, case-ID extraction, diversity cap,
exact-match boost, query classification, and RRF blend scores.

All tests are pure-logic — no network calls, no database, no LLM.
"""

import os

import pytest

# Ensure env vars are set so the class can be instantiated in offline tests.
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from src.services.retrieval.search import HybridRetrieval


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def retrieval() -> HybridRetrieval:
    """Create an instance with dummy credentials (no real connection needed)."""
    return HybridRetrieval(url="http://localhost:54321", key="test-key")


def _make_chunk(chunk_id: str, text: str = "", case_id: str = "", score: float = 0.5) -> dict:
    """Helper: create a minimal search-result chunk dict."""
    return {
        "id": chunk_id,
        "text": text,
        "source": "case_law",
        "metadata": {"case_id": case_id},
        "score": score,
    }


# ---------------------------------------------------------------------------
# rrf_merge
# ---------------------------------------------------------------------------
class TestRRFMerge:
    """Test Reciprocal Rank Fusion merging logic."""

    def test_disjoint_results_get_individual_scores(self, retrieval: HybridRetrieval) -> None:
        """Chunks appearing in only one source get a single RRF contribution."""
        vec = [{"id": "a"}, {"id": "b"}]
        fts = [{"id": "c"}, {"id": "d"}]
        merged = retrieval.rrf_merge(vec, fts, k=60)

        ids = [m["id"] for m in merged]
        assert set(ids) == {"a", "b", "c", "d"}
        # Each chunk should have only one non-zero rank contribution
        for m in merged:
            assert m["rrf_score"] > 0

    def test_overlapping_results_get_combined_score(self, retrieval: HybridRetrieval) -> None:
        """A chunk appearing in both sources should have a higher RRF score."""
        vec = [{"id": "shared"}, {"id": "vec_only"}]
        fts = [{"id": "shared"}, {"id": "fts_only"}]
        merged = retrieval.rrf_merge(vec, fts, k=60)

        scores = {m["id"]: m["rrf_score"] for m in merged}
        assert scores["shared"] > scores["vec_only"]
        assert scores["shared"] > scores["fts_only"]

    def test_empty_inputs_return_empty(self, retrieval: HybridRetrieval) -> None:
        """Merging two empty lists should produce an empty list."""
        assert retrieval.rrf_merge([], []) == []

    def test_single_source_returns_all(self, retrieval: HybridRetrieval) -> None:
        """When only one source has results, all its chunks should appear."""
        vec = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        merged = retrieval.rrf_merge(vec, [])
        assert len(merged) == 3

    def test_ranks_are_recorded(self, retrieval: HybridRetrieval) -> None:
        """Merged results should carry vector_rank and fts_rank metadata."""
        vec = [{"id": "x"}]
        fts = [{"id": "x"}]
        merged = retrieval.rrf_merge(vec, fts)
        assert merged[0]["vector_rank"] == 1
        assert merged[0]["fts_rank"] == 1

    def test_sorted_descending_by_rrf_score(self, retrieval: HybridRetrieval) -> None:
        """Merged list should be sorted by rrf_score descending."""
        vec = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        fts = [{"id": "c"}, {"id": "b"}, {"id": "a"}]
        merged = retrieval.rrf_merge(vec, fts)
        scores = [m["rrf_score"] for m in merged]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# extract_case_ids
# ---------------------------------------------------------------------------
class TestExtractCaseIds:
    """Test case-ID extraction regex."""

    def test_modern_format_colon(self) -> None:
        assert HybridRetrieval.extract_case_ids("KKO:2024:76") == ["KKO:2024:76"]

    def test_modern_format_space(self) -> None:
        assert HybridRetrieval.extract_case_ids("KKO 2024:76") == ["KKO:2024:76"]

    def test_kho_format(self) -> None:
        assert HybridRetrieval.extract_case_ids("KHO:2023:5") == ["KHO:2023:5"]

    def test_multiple_ids(self) -> None:
        ids = HybridRetrieval.extract_case_ids("KKO:2022:18 ja KHO:2023:5")
        assert ids == ["KKO:2022:18", "KHO:2023:5"]

    def test_no_match(self) -> None:
        assert HybridRetrieval.extract_case_ids("some random text") == []

    def test_deduplication(self) -> None:
        ids = HybridRetrieval.extract_case_ids("KKO:2024:1 KKO:2024:1")
        assert ids == ["KKO:2024:1"]

    def test_case_insensitive(self) -> None:
        ids = HybridRetrieval.extract_case_ids("kko:2024:1")
        assert ids == ["KKO:2024:1"]


# ---------------------------------------------------------------------------
# _smart_diversity_cap
# ---------------------------------------------------------------------------
class TestSmartDiversityCap:
    """Test the per-case diversity cap logic."""

    def test_respects_max_per_case(self) -> None:
        """After the top-2 uncapped slots, max_per_case should be enforced."""
        results = [_make_chunk(f"c{i}", case_id="CASE_A") for i in range(10)]
        capped = HybridRetrieval._smart_diversity_cap(results, max_per_case=3, top_k=15)
        # Top 2 uncapped + 1 more from cap (3 total for CASE_A)
        assert len(capped) == 3

    def test_exempt_case_ids_bypass_cap(self) -> None:
        """Exempt case IDs should not be limited by the cap."""
        results = [_make_chunk(f"c{i}", case_id="CASE_A") for i in range(10)]
        capped = HybridRetrieval._smart_diversity_cap(results, max_per_case=2, top_k=15, exempt_case_ids={"CASE_A"})
        assert len(capped) == 10

    def test_top_k_respected(self) -> None:
        """Should never return more than top_k results."""
        results = [_make_chunk(f"c{i}", case_id=f"CASE_{i}") for i in range(20)]
        capped = HybridRetrieval._smart_diversity_cap(results, max_per_case=3, top_k=5)
        assert len(capped) == 5

    def test_small_input_returned_as_is(self) -> None:
        """2 or fewer results should be returned without capping."""
        results = [_make_chunk("c1", case_id="X"), _make_chunk("c2", case_id="X")]
        capped = HybridRetrieval._smart_diversity_cap(results, max_per_case=1, top_k=15)
        assert len(capped) == 2


# ---------------------------------------------------------------------------
# _classify_query
# ---------------------------------------------------------------------------
class TestClassifyQuery:
    """Test query type classification."""

    def test_statute_interpretation(self) -> None:
        assert HybridRetrieval._classify_query("OYL 5:21 soveltaminen") == "statute_interpretation"

    def test_statute_finnish_form(self) -> None:
        assert HybridRetrieval._classify_query("10 luvun 3 § tulkinta") == "statute_interpretation"

    def test_conditions_query(self) -> None:
        assert HybridRetrieval._classify_query("Milloin voidaan myöntää?") == "conditions"

    def test_conditions_edellytykset(self) -> None:
        assert HybridRetrieval._classify_query("edellytykset turvaamistoimelle") == "conditions"

    def test_jurisdiction_query(self) -> None:
        assert HybridRetrieval._classify_query("Mikä tuomioistuin käsittelee?") == "jurisdiction"

    def test_liability_query(self) -> None:
        assert HybridRetrieval._classify_query("vahingonkorvaus työnantajan vastuu") == "liability"

    def test_general_query(self) -> None:
        assert HybridRetrieval._classify_query("kertoo tästä") == "general"


# ---------------------------------------------------------------------------
# _compute_exact_match_boost
# ---------------------------------------------------------------------------
class TestExactMatchBoost:
    """Test exact-match boost computation."""

    def test_no_match_returns_base_boost(self, retrieval: HybridRetrieval) -> None:
        chunk = _make_chunk("c1", text="Random content here")
        boost = retrieval._compute_exact_match_boost(chunk, "some query")
        assert boost == pytest.approx(1.0, abs=0.01)

    def test_statute_match_doubles_boost(self, retrieval: HybridRetrieval) -> None:
        chunk = _make_chunk("c1", text="OYL 5:21 defines the procedure")
        boost = retrieval._compute_exact_match_boost(chunk, "OYL 5:21 soveltaminen")
        assert boost >= 2.0

    def test_case_id_match_boosts(self, retrieval: HybridRetrieval) -> None:
        chunk = {
            "id": "c1",
            "text": "Some case content",
            "metadata": {"case_id": "KKO:2024:1"},
            "score": 0.5,
        }
        boost = retrieval._compute_exact_match_boost(chunk, "KKO:2024:1")
        assert boost >= 1.5


# ---------------------------------------------------------------------------
# _rrf_blend_scores
# ---------------------------------------------------------------------------
class TestRRFBlendScores:
    """Test rerank + pre-rerank blending via RRF."""

    def test_blend_adds_both_contributions(self, retrieval: HybridRetrieval) -> None:
        items = [
            {"id": "a", "rerank_score": 0.9, "score": 0.1},
            {"id": "b", "rerank_score": 0.1, "score": 0.9},
        ]
        blended = retrieval._rrf_blend_scores(items, k=60)
        # Both should have blended_score > 0
        for item in blended:
            assert item["blended_score"] > 0
        # Result should be sorted descending
        scores = [item["blended_score"] for item in blended]
        assert scores == sorted(scores, reverse=True)

    def test_single_item(self, retrieval: HybridRetrieval) -> None:
        items = [{"id": "x", "rerank_score": 0.5, "score": 0.5}]
        blended = retrieval._rrf_blend_scores(items)
        assert len(blended) == 1
        assert blended[0]["blended_score"] > 0
