# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL. Unauthorized copying, distribution, or use is strictly prohibited.

"""
Unit tests for HybridRetrieval: RRF merge, case-ID extraction, diversity cap,
exact-match boost, query classification, and RRF blend scores.

All tests are pure-logic — no network calls, no database, no LLM.
"""

import pytest

from src.services.retrieval.search import HybridRetrieval
from tests.helpers import make_search_chunk


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def retrieval() -> HybridRetrieval:
    """Create an instance with test credentials (no real connection in unit tests)."""
    return HybridRetrieval(url="http://localhost:54321", key="test-key")


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

    def test_none_input_treated_as_empty(self, retrieval: HybridRetrieval) -> None:
        """None in result lists should be treated as empty, not raise."""
        merged = retrieval.rrf_merge(None, [{"id": "a"}])
        assert len(merged) == 1
        assert merged[0]["id"] == "a"

    def test_single_source_returns_all(self, retrieval: HybridRetrieval) -> None:
        """When only one source has results, all its chunks should appear."""
        vec = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        merged = retrieval.rrf_merge(vec, [])
        assert len(merged) == 3

    def test_three_sources_boost_shared_higher(self, retrieval: HybridRetrieval) -> None:
        """A chunk appearing in three sources should score higher than two."""
        vec = [{"id": "shared"}, {"id": "vec_only"}]
        fts = [{"id": "shared"}, {"id": "fts_only"}]
        meta = [{"id": "shared"}, {"id": "meta_only"}]
        merged = retrieval.rrf_merge(vec, fts, meta, k=60)

        scores = {m["id"]: m["rrf_score"] for m in merged}
        assert scores["shared"] > scores["vec_only"]
        assert scores["shared"] > scores["fts_only"]
        assert scores["shared"] > scores["meta_only"]

    def test_sorted_descending_by_rrf_score(self, retrieval: HybridRetrieval) -> None:
        """Merged list should be sorted by rrf_score descending."""
        vec = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        fts = [{"id": "c"}, {"id": "b"}, {"id": "a"}]
        merged = retrieval.rrf_merge(vec, fts)
        scores = [m["rrf_score"] for m in merged]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# _build_fts_query
# ---------------------------------------------------------------------------
class TestBuildFtsQuery:
    """Test Finnish FTS query builder."""

    def test_strips_stop_words_and_joins_with_or(self, retrieval: HybridRetrieval) -> None:
        query = "Onko vahingonkorvauslain 7 luvun 4 §:n oikeuspaikkasäännös pakottava vai tahdonvaltainen?"
        result = retrieval._build_fts_query(query)
        assert "OR" in result
        assert "onko" not in result.lower().split(" or ")
        assert "vai" not in result.lower().split(" or ")
        assert "luvun" not in result.lower().split(" or ")
        assert "vahingonkorvauslain" in result.lower()
        assert "oikeuspaikkasäännös" in result.lower()

    def test_removes_numbers_and_short_tokens(self, retrieval: HybridRetrieval) -> None:
        query = "RL 10 luvun 3 §:n soveltaminen"
        result = retrieval._build_fts_query(query)
        # "10", "3" are pure digits → removed; "RL" is 2 chars → removed
        assert "10" not in result.split(" OR ")
        assert "soveltaminen" in result.lower()

    def test_empty_when_all_stop_words(self, retrieval: HybridRetrieval) -> None:
        query = "onko vai?"
        result = retrieval._build_fts_query(query)
        # Returns empty so callers can short-circuit (skip RPC)
        assert result == ""

    def test_caps_at_eight_terms(self, retrieval: HybridRetrieval) -> None:
        query = "aaa bbb ccc ddd eee fff ggg hhh iii jjj kkk"
        result = retrieval._build_fts_query(query)
        assert result.count(" OR ") <= 7  # 8 terms → 7 ORs


# ---------------------------------------------------------------------------
# _build_prefix_tsquery
# ---------------------------------------------------------------------------
class TestBuildPrefixTsquery:
    """Test prefix-matching query builder for compound Finnish words."""

    def test_generates_prefix_variants_for_long_words(self, retrieval: HybridRetrieval) -> None:
        query = "oikeuspaikkasäännös"
        result = retrieval._build_prefix_tsquery(query)
        assert ":*" in result
        assert "oikeuspaikka:*" in result  # 65% truncation of 18-char word

    def test_no_prefix_for_short_words(self, retrieval: HybridRetrieval) -> None:
        result = retrieval._build_prefix_tsquery("KKO tuomio")
        assert ":*" not in result
        assert "kko" in result
        assert "tuomio" in result

    def test_and_groups_for_two_compounds(self, retrieval: HybridRetrieval) -> None:
        result = retrieval._build_prefix_tsquery("vahingonkorvauslain oikeuspaikkasäännös")
        assert "&" in result  # AND between compound groups
        assert "|" in result  # OR within each group

    def test_empty_for_all_stop_words(self, retrieval: HybridRetrieval) -> None:
        assert retrieval._build_prefix_tsquery("onko vai?") == ""

    def test_none_query_returns_empty(self, retrieval: HybridRetrieval) -> None:
        assert retrieval._build_prefix_tsquery(None) == ""


# ---------------------------------------------------------------------------
# Edge cases: None / empty inputs (FTS and AND-FTS)
# ---------------------------------------------------------------------------
class TestFtsQueryEdgeCases:
    """Test FTS query builders handle None and empty inputs gracefully."""

    def test_build_fts_query_none_returns_empty(self, retrieval: HybridRetrieval) -> None:
        assert retrieval._build_fts_query(None) == ""

    def test_build_and_fts_query_none_returns_empty(self, retrieval: HybridRetrieval) -> None:
        assert retrieval._build_and_fts_query(None) == ""


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

    def test_none_query_returns_empty(self) -> None:
        assert HybridRetrieval.extract_case_ids(None) == []

    def test_empty_string_returns_empty(self) -> None:
        assert HybridRetrieval.extract_case_ids("") == []


# ---------------------------------------------------------------------------
# _smart_diversity_cap
# ---------------------------------------------------------------------------
class TestSmartDiversityCap:
    """Test the per-case diversity cap logic."""

    def test_respects_max_per_case(self) -> None:
        """After the top-2 uncapped slots, max_per_case should be enforced."""
        results = [make_search_chunk(f"c{i}", case_id="CASE_A") for i in range(10)]
        capped = HybridRetrieval._smart_diversity_cap(results, max_per_case=3, top_k=15)
        # Top 2 uncapped + 1 more from cap (3 total for CASE_A)
        assert len(capped) == 3

    def test_exempt_case_ids_bypass_cap(self) -> None:
        """Exempt case IDs should not be limited by the cap."""
        results = [make_search_chunk(f"c{i}", case_id="CASE_A") for i in range(10)]
        capped = HybridRetrieval._smart_diversity_cap(results, max_per_case=2, top_k=15, exempt_case_ids={"CASE_A"})
        assert len(capped) == 10

    def test_top_k_respected(self) -> None:
        """Should never return more than top_k results."""
        results = [make_search_chunk(f"c{i}", case_id=f"CASE_{i}") for i in range(20)]
        capped = HybridRetrieval._smart_diversity_cap(results, max_per_case=3, top_k=5)
        assert len(capped) == 5

    def test_small_input_returned_as_is(self) -> None:
        """2 or fewer results should be returned without capping."""
        results = [make_search_chunk("c1", case_id="X"), make_search_chunk("c2", case_id="X")]
        capped = HybridRetrieval._smart_diversity_cap(results, max_per_case=1, top_k=15)
        assert len(capped) == 2

    def test_none_results_returns_empty(self) -> None:
        """None results should be treated as empty list."""
        capped = HybridRetrieval._smart_diversity_cap(None, max_per_case=3, top_k=15)
        assert capped == []


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

    def test_none_query_returns_general(self) -> None:
        assert HybridRetrieval._classify_query(None) == "general"


# ---------------------------------------------------------------------------
# _compute_exact_match_boost
# ---------------------------------------------------------------------------
class TestExactMatchBoost:
    """Test exact-match boost computation."""

    def test_no_match_returns_base_boost(self, retrieval: HybridRetrieval) -> None:
        chunk = make_search_chunk("c1", text="Random content here")
        boost = retrieval._compute_exact_match_boost(chunk, "some query")
        assert boost == pytest.approx(1.0, abs=0.01)

    def test_statute_match_doubles_boost(self, retrieval: HybridRetrieval) -> None:
        chunk = make_search_chunk("c1", text="OYL 5:21 defines the procedure")
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

    def test_none_chunk_returns_base_boost(self, retrieval: HybridRetrieval) -> None:
        boost = retrieval._compute_exact_match_boost(None, "some query")
        assert boost == pytest.approx(1.0)

    def test_none_query_returns_base_boost(self, retrieval: HybridRetrieval) -> None:
        chunk = make_search_chunk("c1", text="content")
        boost = retrieval._compute_exact_match_boost(chunk, None)
        assert boost == pytest.approx(1.0)


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

    def test_none_reranked_returns_empty(self, retrieval: HybridRetrieval) -> None:
        blended = retrieval._rrf_blend_scores(None)
        assert blended == []


# ---------------------------------------------------------------------------
# _build_and_fts_query
# ---------------------------------------------------------------------------
class TestBuildAndFtsQuery:
    """Test AND-based FTS query builder (high-precision channel)."""

    def test_joins_top_three_terms_with_spaces(self, retrieval: HybridRetrieval) -> None:
        """AND query should contain space-separated terms (implicit AND for websearch_to_tsquery)."""
        query = "osamaksumyyjä vaatia takaisinsaantia kolmannelta osapuolelta"
        result = retrieval._build_and_fts_query(query)
        # Should NOT contain OR
        assert "OR" not in result
        # Should contain at most 3 terms
        terms = result.split()
        assert len(terms) <= 3
        # Longest terms should be selected (sorted by length descending)
        assert "osamaksumyyjä" in result.lower()
        assert "takaisinsaantia" in result.lower()

    def test_empty_when_fewer_than_two_terms(self, retrieval: HybridRetrieval) -> None:
        """AND of a single term adds no value over OR — should return empty."""
        # "onko" is a stopword, "laki" is the only surviving term
        result = retrieval._build_and_fts_query("onko laki?")
        assert result == ""

    def test_preserves_three_terms_max(self, retrieval: HybridRetrieval) -> None:
        """Should keep at most 3 terms even with many input words."""
        query = "vahingonkorvauslain oikeuspaikkasäännös työsopimus irtisanominen"
        result = retrieval._build_and_fts_query(query)
        terms = result.split()
        assert len(terms) == 3

    def test_empty_for_all_stop_words(self, retrieval: HybridRetrieval) -> None:
        result = retrieval._build_and_fts_query("onko vai?")
        assert result == ""


# ---------------------------------------------------------------------------
# _title_keyword_overlap_boost
# ---------------------------------------------------------------------------
class TestTitleKeywordOverlapBoost:
    """Test title keyword overlap boost logic."""

    def test_no_boost_when_no_title(self) -> None:
        """Should return 1.0 when chunk has no case_title."""
        chunk = make_search_chunk("c1", text="content")
        boost = HybridRetrieval._title_keyword_overlap_boost(
            chunk, "osamaksumyyjä takaisinsaantia", {"osamaksumyyjä", "takaisinsaantia"}
        )
        assert boost == pytest.approx(1.0)

    def test_no_boost_when_short_words_only(self) -> None:
        """Words shorter than 6 chars should not trigger the title boost."""
        chunk = {
            "id": "c1",
            "text": "",
            "metadata": {"case_id": "KKO:2020:1", "case_title": "Rikos - Tuomio"},
            "score": 0.5,
        }
        boost = HybridRetrieval._title_keyword_overlap_boost(chunk, "rikos tuomio", {"rikos", "tuomio"})
        # Both words < 6 chars: "rikos" = 5, "tuomio" = 6 → tuomio passes but only 1 root → 1.0
        assert boost == pytest.approx(1.0)

    def test_boost_when_two_roots_match(self) -> None:
        """Should return 1.3 when 2 query root prefixes appear in the title."""
        chunk = {
            "id": "c1",
            "text": "",
            "metadata": {"case_id": "KKO:1987:124", "case_title": "Osamaksukauppa - Takaisinsaanti"},
            "score": 0.5,
        }
        # "osamak" (6 chars) is in "Osamaksukauppa", "takais" (6 chars) is in "Takaisinsaanti"
        boost = HybridRetrieval._title_keyword_overlap_boost(
            chunk,
            "osamaksumyyjä takaisinsaantia kolmannelta",
            {"osamaksumyyjä", "takaisinsaantia", "kolmannelta"},
        )
        assert boost >= 1.3

    def test_higher_boost_for_three_roots(self) -> None:
        """Should return 1.6 when 3+ query root prefixes appear in the title."""
        chunk = {
            "id": "c1",
            "text": "",
            "metadata": {"case_id": "X", "case_title": "Osamaksukauppa - Takaisinsaanti - Kolmansien"},
            "score": 0.5,
        }
        boost = HybridRetrieval._title_keyword_overlap_boost(
            chunk,
            "osamaksumyyjä takaisinsaantia kolmansien osapuolelta",
            {"osamaksumyyjä", "takaisinsaantia", "kolmansien", "osapuolelta"},
        )
        assert boost >= 1.6
