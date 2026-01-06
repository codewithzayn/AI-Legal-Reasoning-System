"""
Agent State Definition for LangGraph
"""

from typing import TypedDict, List, Optional


class AgentState(TypedDict):
    """
    State object passed through the LangGraph workflow
    """
    # User input
    query: str
    
    # Conversation history
    messages: List[dict]
    
    # Processing stages (for tracking)
    stage: str  # current stage: analyze, search, reason, respond
    
    # Extracted entities (future: from NLP)
    entities: Optional[List[dict]]

    # Search results (future: from vector DB)
    search_results: Optional[List[dict]]
    
    # Final response
    response: str
    
    # Error handling
    error: Optional[str]
