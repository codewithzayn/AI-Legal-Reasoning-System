"""
LangGraph Node Functions (Abstraction Layer)
Each node represents a processing stage in the workflow
"""

from typing import Dict, Any
from .state import AgentState
from ..services.retrieval import HybridRetrieval
from ..services.llm_generator import LLMGenerator


def search_knowledge(state: AgentState) -> AgentState:
    """
    Node 2: Search knowledge base using hybrid retrieval
    
    Combines vector search (semantic) and full-text search (keywords)
    using Reciprocal Rank Fusion (RRF) to find relevant legal documents.
    
    Returns top 20-30 most relevant chunks from Supabase.
    """
    state["stage"] = "search"
    
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
        
        # Store results in state
        state["search_results"] = results
        state["rrf_results"] = results
        
        # Store metadata for debugging
        state["retrieval_metadata"] = {
            "total_results": len(results),
            "query": query,
            "method": "hybrid_rrf_rerank"
        }
        
    except Exception as e:
        print(f"Search error: {e}")
        state["search_results"] = []
        state["error"] = f"Search failed: {str(e)}"
    
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
        state["response"] = "Annettujen asiakirjojen perusteella en löydä tietoa tästä aiheesta. Tietokannassa ei ole relevantteja asiakirjoja."
        return state
    
    # Generate response with LLM
    try:
        llm = LLMGenerator()
        response = llm.generate_response(
            query=state["query"],
            context_chunks=results
        )
        state["response"] = response
    except Exception as e:
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
