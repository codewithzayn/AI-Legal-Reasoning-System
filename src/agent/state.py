"""
Agent State Definition for LangGraph
"""

from typing import TypedDict


class AgentState(TypedDict):
    """
    State object passed through the LangGraph workflow.

    Tracks query processing through: analyze → search → reason → respond
    """

    # User input
    query: str

    # Conversation history
    messages: list[dict]

    # Processing stages (for tracking)
    stage: str  # current stage: search, reason, respond

    # Search results from hybrid retrieval (Vector + FTS + RRF)
    vector_results: list[dict] | None  # Top 50 from vector similarity
    fts_results: list[dict] | None  # Top 50 from full-text search
    rrf_results: list[dict] | None  # Top 20-30 after RRF merge
    search_results: list[dict] | None  # Final ranked results

    # Retrieval metadata (for debugging/monitoring)
    retrieval_metadata: dict | None

    # Intent routing
    intent: str  # 'legal_search', 'general', 'clarification'

    # Self-correction
    original_query: str
    search_attempts: int  # To prevent infinite loops

    # Final response
    response: str

    # Relevancy check (post-answer LLM; compact input to respect context)
    relevancy_score: float | None
    relevancy_reason: str | None

    # Error handling
    error: str | None

    # Response language: "en" | "fi" | "sv" (matches UI language selector)
    response_lang: str | None

    # Year filter for case-law search (inclusive). When set, only cases in this range.
    year_start: int | None
    year_end: int | None

    # True when UI detected year clarification reply (user already answered; do not ask again).
    year_clarification_answered: bool

    # Optional queue for streaming LLM tokens (reason node puts chunks here)
    stream_queue: object | None

    # UI search filters (optional, from sidebar controls)
    court_types: list[str] | None  # e.g. ["KKO", "KHO"]
    legal_domains: list[str] | None  # e.g. ["Criminal", "Civil"]

    # Multi-tenant: client document isolation
    tenant_id: str | None  # from LEXAI_TENANT_ID env var or session state
