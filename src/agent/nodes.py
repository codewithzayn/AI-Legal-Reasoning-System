"""
LangGraph Node Functions (Abstraction Layer)
Each node represents a processing stage in the workflow
"""

import time
from typing import Dict, Any, Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from .state import AgentState
from ..services.retrieval import HybridRetrieval
from ..services.llm_generator import LLMGenerator
from src.config.logging_config import setup_logger
logger = setup_logger(__name__)


def analyze_intent(state: AgentState) -> AgentState:
    """
    Node 1: Analyze User Intent
    
    Classifies query into: 'legal_search', 'general_chat', 'clarification'
    """
    state["stage"] = "analyze"
    query = state["query"]
    
    # Store original query if not set
    if not state.get("original_query"):
        state["original_query"] = query
        state["search_attempts"] = 0
    
    logger.info(f"[ANALYZE] Classifying intent for: {query}")
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    system_prompt = """Classify the user's input into exactly one category:
    1. 'legal_search': Questions about Finnish law, court cases, penalties, rights, or legal definitions.
    2. 'general_chat': Greetings (Hi, Hello), thanks, or questions about you (Who are you?).
    3. 'clarification': The query is too vague to search (e.g., "What is the penalty?", "Does it apply?").

    Return ONLY the category name.
    """
    
    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=query)
        ])
        intent = response.content.strip().lower()
        if intent not in ['legal_search', 'general_chat', 'clarification']:
            intent = 'legal_search' # Default safe fallback
            
        logger.info(f"[ANALYZE] Intent matched: {intent}")
        # Return partial update
        return {"intent": intent, "stage": "analyze", "original_query": state.get("original_query", query), "search_attempts": 0}
        
    except Exception as e:
        logger.error(f"[ANALYZE] Error: {e}")
        return {"intent": "legal_search", "stage": "analyze"}


def reformulate_query(state: AgentState) -> AgentState:
    """
    Node: Reformulate Query (Self-Correction)
    
    Rewrites the search query to improve retrieval results.
    """
    state["stage"] = "reformulate"
    original = state.get("original_query", state["query"])
    attempts = state.get("search_attempts", 0) + 1
    state["search_attempts"] = attempts
    
    logger.info(f"[REFORMULATE] Attempt {attempts}: Rewriting query...")
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
    
    system_prompt = """You are a legal search expert. The previous search found 0 results.
    Rewrite the user's query to be a better keyword search for a Finnish legal database (Finlex/Case Law).
    
    Rules:
    - Extract core legal concepts.
    - Remove noise words.
    - Include synonyms if helpful.
    - Output ONLY the new search string in Finnish.
    """
    
    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=original)
        ])
        new_query = response.content.strip()
        state["query"] = new_query
        logger.info(f"[REFORMULATE] New query: {new_query}")
        
    except Exception as e:
        logger.error(f"[REFORMULATE] Error: {e}")
        
    return state


def ask_clarification(state: AgentState) -> AgentState:
    """
    Node: Ask Clarification
    
    Asks the user to be more specific.
    """
    state["stage"] = "clarify"
    query = state["query"]
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    
    try:
        response = llm.invoke([
            SystemMessage(content="The user's legal question is too vague. Ask a polite follow-up question in Finnish to clarify what they are looking for."),
            HumanMessage(content=query)
        ])
        state["response"] = response.content
    except Exception:
        state["response"] = "Voisitko tarkentaa kysymystäsi? En ole varma mitä asiaa tarkoitat."
        
    return state


def general_chat(state: AgentState) -> AgentState:
    """
    Node: General Chat
    
    Handles non-legal conversation.
    """
    state["stage"] = "chat"
    query = state["query"]
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.5)
    
    system_prompt = """You are a helpful Finnish Legal Assistant.
    The user is engaging in general chat (greetings/thanks).
    Respond politely in Finnish.
    If they ask who you are, explain that you are an AI assistant specialized in Finnish legislation and case law (KKO/KHO).
    """
    
    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=query)
        ])
        state["response"] = response.content
    except Exception:
        state["response"] = "Hei! Kuinka voin auttaa sinua oikeudellisissa asioissa?"
        
    return state



async def search_knowledge(state: AgentState) -> AgentState:
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
        results = await retrieval.hybrid_search_with_rerank(
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
