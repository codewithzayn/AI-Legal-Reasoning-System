"""
Main agent interface for Finnish Legal Reasoning System
"""

import time
from typing import Any

from src.config.logging_config import setup_logger

from .graph import agent_graph
from .state import AgentState
from .stream import _strip_relevancy_line

logger = setup_logger(__name__)


def process_query(user_query: str, chat_history: list = None) -> str:
    """
    Process user query through LangGraph agent

    Args:
        user_query: User's question
        chat_history: Previous conversation (optional)

    Returns:
        Agent's response string
    """

    total_start = time.time()
    logger.info(f"QUERY: {user_query}")

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
        "relevancy_score": None,
        "relevancy_reason": None,
        "error": None,
    }

    try:
        # Run agent
        final_state = agent_graph.invoke(initial_state)

        total_elapsed = time.time() - total_start
        logger.info(f"TOTAL TIME: {total_elapsed:.2f}s")

        resp = final_state.get("response", "Error: No response generated")
        return _strip_relevancy_line(resp)

    except Exception:
        # Error handling
        logger.exception("Agent execution failed")
        return "An internal error occurred. Please check the logs for details or try again later."


def get_agent_info() -> dict[str, Any]:
    """
    Get agent configuration and status
    """
    return {
        "name": "Finnish Legal Reasoning Agent",
        "version": "0.3.0",
        "workflow_stages": ["search", "reason", "respond"],
        "integrations": {
            "vector_db": "Supabase pgvector (active)",
            "fts": "PostgreSQL ts_rank (active)",
            "rrf": "Reciprocal Rank Fusion (active)",
            "reranker": "Cohere Rerank v4.0-fast (active)",
            "llm": "GPT-4o mini (active)",
        },
        "status": "Full RAG pipeline active",
    }
