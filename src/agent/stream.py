"""
Streaming version of agent for Streamlit
"""

from typing import Iterator
from .state import AgentState
from .graph import agent_graph
from ..services.retrieval import HybridRetrieval
from ..services.llm_generator import LLMGenerator
from src.config.logging_config import setup_logger
import time
logger = setup_logger(__name__)


from typing import AsyncIterator

async def stream_query_response(user_query: str) -> AsyncIterator[str]:
    """
    Stream response from agent
    
    Args:
        user_query: User's question
        
    Yields:
        Response chunks as they're generated
    """
    total_start = time.time()
    logger.info(f"QUERY: {user_query}")
    
    # Step 1: Search (non-streaming)
    logger.info("[SEARCH] Starting hybrid search + reranking...")
    search_start = time.time()
    
    retrieval = HybridRetrieval()
    results = await retrieval.hybrid_search_with_rerank(
        user_query, 
        initial_limit=20, 
        final_limit=5
    )
    
    search_elapsed = time.time() - search_start
    logger.info(f"[SEARCH] Completed in {search_elapsed:.2f}s - Retrieved {len(results)} results")
    
    # Step 2: Stream LLM response
    if not results:
        yield "Annettujen asiakirjojen perusteella en löydä tietoa tästä aiheesta. Tietokannassa ei ole relevantteja asiakirjoja."
        return
    
    logger.info(f"[LLM] Streaming response with {len(results)} chunks...")
    llm_start = time.time()
    
    llm = LLMGenerator()
    for chunk in llm.stream_response(user_query, results):
        yield chunk
    
    llm_elapsed = time.time() - llm_start
    total_elapsed = time.time() - total_start
    
    logger.info(f"[LLM] Completed in {llm_elapsed:.2f}s")
    logger.info(f"TOTAL TIME: {total_elapsed:.2f}s")
