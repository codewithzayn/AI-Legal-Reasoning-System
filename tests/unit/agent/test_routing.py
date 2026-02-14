# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL. Unauthorized copying, distribution, or use is strictly prohibited.

"""
Unit tests for agent routing logic: route_intent, route_search_result,
and the _is_obvious_legal_query fast-path helper.

All tests are pure-logic — no LLM calls, no network.
"""

import os

# Set env vars before importing modules that trigger settings/config loading.
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from src.agent.graph import route_intent, route_search_result
from src.agent.nodes import _is_obvious_legal_query


# ---------------------------------------------------------------------------
# route_intent
# ---------------------------------------------------------------------------
class TestRouteIntent:
    """Test the intent → node routing function."""

    def test_legal_search_routes_to_search(self) -> None:
        state = {"intent": "legal_search"}
        assert route_intent(state) == "search"

    def test_general_chat_routes_to_chat(self) -> None:
        state = {"intent": "general_chat"}
        assert route_intent(state) == "chat"

    def test_clarification_routes_to_clarify(self) -> None:
        state = {"intent": "clarification"}
        assert route_intent(state) == "clarify"

    def test_unknown_intent_defaults_to_search(self) -> None:
        state = {"intent": "something_unexpected"}
        assert route_intent(state) == "search"

    def test_missing_intent_defaults_to_search(self) -> None:
        state = {}
        assert route_intent(state) == "search"


# ---------------------------------------------------------------------------
# route_search_result
# ---------------------------------------------------------------------------
class TestRouteSearchResult:
    """Test the search-result → next-node routing."""

    def test_results_found_routes_to_reason(self) -> None:
        state = {"search_results": [{"id": "chunk1"}], "search_attempts": 1}
        assert route_search_result(state) == "reason"

    def test_no_results_first_attempt_routes_to_reformulate(self) -> None:
        state = {"search_results": [], "search_attempts": 1}
        assert route_search_result(state) == "reformulate"

    def test_no_results_max_attempts_routes_to_reason(self) -> None:
        """After 2 failed attempts (max), give up and route to reason (apology)."""
        state = {"search_results": [], "search_attempts": 2}
        assert route_search_result(state) == "reason"

    def test_no_results_third_attempt_still_routes_to_reason(self) -> None:
        """Anything above max attempts still routes to reason."""
        state = {"search_results": [], "search_attempts": 3}
        assert route_search_result(state) == "reason"

    def test_missing_results_key_defaults_to_reformulate(self) -> None:
        state = {"search_attempts": 1}
        assert route_search_result(state) == "reformulate"


# ---------------------------------------------------------------------------
# _is_obvious_legal_query
# ---------------------------------------------------------------------------
class TestIsObviousLegalQuery:
    """Test the fast-path legal query detection."""

    def test_kko_reference_is_legal(self) -> None:
        assert _is_obvious_legal_query("KKO:2024:1 tuomio") is True

    def test_statute_reference_is_legal(self) -> None:
        assert _is_obvious_legal_query("Rikoslain 21 § soveltaminen") is True

    def test_short_greeting_is_not_legal(self) -> None:
        assert _is_obvious_legal_query("Hei") is False

    def test_empty_string_is_not_legal(self) -> None:
        assert _is_obvious_legal_query("") is False

    def test_long_query_is_legal(self) -> None:
        """Queries longer than 40 chars are treated as legal (likely substantive)."""
        long_query = "Miten yhtiökokous voidaan määrätä pidettäväksi tuomioistuimen päätöksellä?"
        assert _is_obvious_legal_query(long_query) is True

    def test_legal_keyword_edellytykset(self) -> None:
        assert _is_obvious_legal_query("edellytykset") is True

    def test_legal_keyword_tuomioistuin(self) -> None:
        assert _is_obvious_legal_query("tuomioistuin") is True

    def test_very_short_nonlegal_is_false(self) -> None:
        assert _is_obvious_legal_query("ab") is False
