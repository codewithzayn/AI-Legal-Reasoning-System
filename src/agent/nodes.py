"""
LangGraph Node Functions (Abstraction Layer)
Each node represents a processing stage in the workflow
"""

import time
from typing import Dict, Any
from .state import AgentState
from ..services.retrieval import HybridRetrieval
from ..services.llm_generator import LLMGenerator
from src.config.logging_config import setup_logger
logger = setup_logger(__name__)


def search_knowledge(state: AgentState) -> AgentState:
    """
    Node 2: Search knowledge base using hybrid retrieval
    
    Performs: Vector Search + FTS + RRF + Cohere Rerank
    """
    state["stage"] = "search"
    start_time = time.time()
    logger.info("[SEARCH] Starting hybrid search + reranking...")
    
    try:
        # Initialize retrieval service
        retrieval = HybridRetrieval()
        
        # Perform hybrid search + reranking
        query = state["query"]
        results = retrieval.hybrid_search_with_rerank(
            query, 
            initial_limit=20, 
            final_limit=10
        )
        
        elapsed = time.time() - start_time
        logger.info(f"[SEARCH] Completed in {elapsed:.2f}s - Retrieved {len(results)} results")
        
        # Store results in state
        state["search_results"] = results
        state["rrf_results"] = results
        
        # Store metadata for debugging
        state["retrieval_metadata"] = {
            "total_results": len(results),
            "query": query,
            "method": "hybrid_rrf_rerank",
            "search_time": elapsed
        }
        
    except Exception as e:
        logger.error(f"[SEARCH] Error: {e}")
        state["error"] = f"Search failed: {str(e)}"
        state["search_results"] = []
    
    return state


def reason_legal(state: AgentState) -> AgentState:
    """
    Node 3: Legal reasoning with LLM
    
    Analyzes search results and generates response with citations
    """
    state["stage"] = "reason"
    
    # Get search results
    results = state.get("search_results", [])
    
    if not results:
        logger.warning("[LLM] No search results found")
        state["response"] = "Annettujen asiakirjojen perusteella en löydä tietoa tästä aiheesta. Tietokannassa ei ole relevantteja asiakirjoja."
        return state
    
    # Generate response with LLM
    start_time = time.time()
    logger.info(f"[LLM] Generating response with {len(results)} chunks...")
    
    try:
        llm = LLMGenerator()
        response = llm.generate_response(
            query=state["query"],
            context_chunks=results
        )
        state["response"] = response
        
        elapsed = time.time() - start_time
        logger.info(f"[LLM] Completed in {elapsed:.2f}s")
        
    except Exception as e:
        logger.error(f"[LLM] Error: {e}")
        state["error"] = f"LLM generation failed: {str(e)}"
        state["response"] = "Pahoittelut, vastauksen luomisessa tapahtui virhe. Yritä uudelleen."
    
    return state


def generate_response(state: AgentState) -> AgentState:
    """
    Node 4: Return final response
    
    Response already generated in reason_legal node
    """
    state["stage"] = "respond"
    
    # Response already set by reason_legal
    if not state.get("response"):
        state["response"] = "Pahoittelut, vastausta ei voitu luoda. Yritä uudelleen."
    
    return state


def handle_error(state: AgentState) -> AgentState:
    """
    Error handler node
    """
    state["stage"] = "error"
    state["response"] = f"❌ Error: {state.get('error', 'Unknown error occurred')}"
    return state
