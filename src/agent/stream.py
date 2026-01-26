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
    initial_state: AgentState = {
        "query": user_query,
        "messages": [],
        "stage": "init",
        "search_attempts": 0,
        "original_query": user_query,
        "intent": "",
        "search_results": [],
        "response": "",
        "error": None
    }
    
    # Stream events from the graph
    # We yield status messages for intermediate steps
    async for event in agent_graph.astream(initial_state):
        for key, value in event.items():
            stage = key
            
            if stage == "analyze":
                yield "🤔 Analysoidaan kysymystä...\n\n"
            
            elif stage == "search":
                count = len(value.get("search_results", []))
                yield f"🔍 Etsitään tietoa... (Löydetty {count} tulosta)\n\n"
            
            elif stage == "reformulate":
                new_query = value.get("query", "")
                yield f"🔄 Hakutuloksia ei löytynyt. Tarkennetaan hakua: '{new_query}'...\n\n"
            
            elif stage == "clarify":
                # Yield the clarification question
                response = value.get("response", "")
                yield response
                return
            
            elif stage == "chat":
                 # Yield the chat response
                response = value.get("response", "")
                yield response
                return

            elif stage == "respond":
                # Yield the final answer
                response = value.get("response", "")
                yield response
                return
                
            elif stage == "error":
                yield f"❌ Virhe: {value.get('error')}"
                return
