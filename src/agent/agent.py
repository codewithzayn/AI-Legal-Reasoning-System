"""
Main Agent Interface
Single entry point for the LangGraph agent
"""

from typing import Dict, Any
from .graph import agent_graph
from .state import AgentState


def process_query(user_query: str, chat_history: list = None) -> str:
    """
    Process user query through LangGraph workflow
    
    Args:
        user_query: User's legal question
        chat_history: Previous conversation messages (optional)
    
    Returns:
        Agent's response string
    """
    
    # Initialize state
    initial_state: AgentState = {
        "query": user_query,
        "messages": chat_history or [],
        "stage": "init",
        "vector_results": None,
        "fts_results": None,
        "rrf_results": None,
        "search_results": None,
        "retrieval_metadata": None,
        "response": "",
        "error": None
    }
    
    try:
        # Run through LangGraph workflow
        final_state = agent_graph.invoke(initial_state)
        
        # Return final response
        return final_state["response"]
    
    except Exception as e:
        # Error handling
        return f"Agent Error: {str(e)}\n\nPlease try again or rephrase your question."


def get_agent_info() -> Dict[str, Any]:
    """
    Get agent configuration and status
    """
    return {
        "name": "Finnish Legal Reasoning Agent",
        "version": "0.2.0",
        "workflow_stages": ["search", "reason", "respond"],
        "integrations": {
            "vector_db": "Supabase pgvector (active)",
            "fts": "PostgreSQL ts_rank (active)",
            "rrf": "Reciprocal Rank Fusion (active)",
            "reranker": "Cohere Rerank v3 (pending)",
            "llm": "GPT-4o (pending)"
        },
        "status": "Hybrid search active - Re-ranking next"
    }
