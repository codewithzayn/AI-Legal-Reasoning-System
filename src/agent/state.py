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
