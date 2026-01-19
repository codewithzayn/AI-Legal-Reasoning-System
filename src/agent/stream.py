"""
Streaming version of agent for Streamlit
"""

from typing import Iterator
from .state import AgentState
from .graph import agent_graph
from ..services.retrieval import HybridRetrieval
from ..services.llm_generator import LLMGenerator
import time


def stream_query_response(user_query: str) -> Iterator[str]:
    """
    Stream response from agent
    
    Args:
        user_query: User's question
        
    Yields:
        Response chunks as they're generated
    """
    total_start = time.time()
    print(f"🔍 QUERY: {user_query}")
    
    # Step 1: Search (non-streaming)
    print(f"\n⏱️  [SEARCH] Starting hybrid search + reranking...")
    search_start = time.time()
    
    retrieval = HybridRetrieval()
    results = retrieval.hybrid_search_with_rerank(
        user_query, 
        initial_limit=20, 
        final_limit=10
    )
    
    search_elapsed = time.time() - search_start
    print(f"✅ [SEARCH] Completed in {search_elapsed:.2f}s - Retrieved {len(results)} results")
    
    # Step 2: Stream LLM response
    if not results:
        yield "Annettujen asiakirjojen perusteella en löydä tietoa tästä aiheesta. Tietokannassa ei ole relevantteja asiakirjoja."
        return
    
    print(f"⏱️  [LLM] Streaming response with {len(results)} chunks...")
    llm_start = time.time()
    
    llm = LLMGenerator()
    for chunk in llm.stream_response(user_query, results):
        yield chunk
    
    llm_elapsed = time.time() - llm_start
    total_elapsed = time.time() - total_start
    
    print(f"✅ [LLM] Completed in {llm_elapsed:.2f}s")
    print(f"⏱️  TOTAL TIME: {total_elapsed:.2f}s")
