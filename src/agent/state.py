"""
Agent State Definition for LangGraph
"""

from typing import TypedDict, List, Optional


class AgentState(TypedDict):
    """
    State object passed through the LangGraph workflow.
    
    Tracks query processing through: analyze → search → reason → respond
    """
    # User input
    query: str
    
    # Conversation history
    messages: List[dict]
    
    # Processing stages (for tracking)
    stage: str  # current stage: search, reason, respond

    # Search results from hybrid retrieval (Vector + FTS + RRF)
    vector_results: Optional[List[dict]]  # Top 50 from vector similarity
    fts_results: Optional[List[dict]]     # Top 50 from full-text search
    rrf_results: Optional[List[dict]]     # Top 20-30 after RRF merge
    search_results: Optional[List[dict]]  # Final ranked results
    
    # Retrieval metadata (for debugging/monitoring)
    retrieval_metadata: Optional[dict]
    
    # Final response
    response: str
    
    # Error handling
    error: Optional[str]
