"""
LangGraph Node Functions (Abstraction Layer)
Each node represents a processing stage in the workflow
"""

import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.config.logging_config import setup_logger
from src.config.settings import config
from src.services.retrieval import HybridRetrieval
from src.services.retrieval.generator import LLMGenerator
from src.services.retrieval.relevancy import check_relevancy

from .state import AgentState

logger = setup_logger(__name__)

# Reusable LLM instances to prevent excessive background task creation
# and resolve "Task destroyed but pending" warnings.
_llm_mini = ChatOpenAI(model="gpt-4o-mini", temperature=0)
_generator = LLMGenerator()


async def analyze_intent(state: AgentState) -> AgentState:
    """
    Node 1: Analyze User Intent (Async)
    """
    state["stage"] = "analyze"
    query = state["query"]

    if not state.get("original_query"):
        state["original_query"] = query
        state["search_attempts"] = 0

    logger.info("Analyzing intent...")

    system_prompt = """Classify the user's input into exactly one category:
    1. 'legal_search': Questions about Finnish law, court cases, penalties, rights, or legal definitions.
    2. 'general_chat': Greetings (Hi, Hello), thanks, or questions about you (Who are you?).
    3. 'clarification': The query is too vague to search (e.g., "What is the penalty?", "Does it apply?").

    Return ONLY the category name.
    """

    try:
        response = await _llm_mini.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=query)])
        intent = response.content.strip().lower()
        if intent not in ["legal_search", "general_chat", "clarification"]:
            intent = "legal_search"

        logger.info(f"Intent: {intent}")
        return {
            "intent": intent,
            "stage": "analyze",
            "original_query": state.get("original_query", query),
            "search_attempts": 0,
        }

    except Exception as e:
        logger.error(f"Intent error: {e}")
        return {"intent": "legal_search", "stage": "analyze"}


async def reformulate_query(state: AgentState) -> AgentState:
    """
    Node: Reformulate Query (Async)
    """
    state["stage"] = "reformulate"
    original = state.get("original_query", state["query"])
    attempts = state.get("search_attempts", 0) + 1
    state["search_attempts"] = attempts

    logger.info(f"[REFORMULATE] Attempt {attempts}: Rewriting query...")

    system_prompt = """You are a legal search expert. The previous search found 0 results.
    Rewrite the user's query to be a better keyword search for a Finnish legal database (Finlex/Case Law).

    Rules:
    - Extract core legal concepts.
    - Remove noise words.
    - Include synonyms if helpful.
    - Output ONLY the new search string in Finnish.
    """

    try:
        response = await _llm_mini.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=original)])
        new_query = response.content.strip()
        state["query"] = new_query
        logger.info(f"[REFORMULATE] New query: {new_query}")

    except Exception as e:
        logger.error(f"[REFORMULATE] Error: {e}")

    return state


async def ask_clarification(state: AgentState) -> AgentState:
    """
    Node: Ask Clarification (Async)
    """
    state["stage"] = "clarify"
    query = state["query"]

    try:
        response = await _llm_mini.ainvoke(
            [
                SystemMessage(
                    content="The user's legal question is too vague. Ask a polite follow-up question in Finnish to clarify what they are looking for."
                ),
                HumanMessage(content=query),
            ]
        )
        state["response"] = response.content
    except Exception:
        state["response"] = "Voisitko tarkentaa kysymystäsi? En ole varma mitä asiaa tarkoitat."

    return state


async def general_chat(state: AgentState) -> AgentState:
    """
    Node: General Chat (Async)
    """
    state["stage"] = "chat"
    query = state["query"]

    system_prompt = """You are a helpful Finnish Legal Assistant.
    The user is engaging in general chat (greetings/thanks).
    Respond politely in Finnish.
    If they ask who you are, explain that you are an AI assistant specialized in Finnish legislation and case law (KKO/KHO).
    """

    try:
        response = await _llm_mini.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=query)])
        state["response"] = response.content
    except Exception:
        state["response"] = "Hei! Kuinka voin auttaa sinua oikeudellisissa asioissa?"

    return state


async def search_knowledge(state: AgentState) -> AgentState:
    """
    Node 2: Search knowledge base using hybrid retrieval (Async)
    """
    state["stage"] = "search"
    start_time = time.time()
    logger.info("Hybrid search → fetching candidates...")
    try:
        retrieval = HybridRetrieval()
        query = state["query"]
        results = await retrieval.hybrid_search_with_rerank(
            query,
            initial_limit=config.SEARCH_CANDIDATES_FOR_RERANK,
            final_limit=config.CHUNKS_TO_LLM,
        )
        elapsed = time.time() - start_time
        logger.info(f"Reranking done → {len(results)} chunks in {elapsed:.1f}s")

        state["search_results"] = results
        state["rrf_results"] = results
        state["retrieval_metadata"] = {
            "total_results": len(results),
            "query": query,
            "method": "hybrid_rrf_rerank",
            "search_time": elapsed,
        }
    except Exception as e:
        logger.error(f"Search error: {e}")
        state["error"] = f"Search failed: {e!s}"
        state["search_results"] = []

    return state


async def reason_legal(state: AgentState) -> AgentState:
    """
    Node 3: Legal reasoning with LLM (Async)
    """
    state["stage"] = "reason"
    results = state.get("search_results", [])

    if not results:
        logger.warning("No search results found")
        state["response"] = (
            "Annettujen asiakirjojen perusteella en löydä tietoa tästä aiheesta. Tietokannassa ei ole relevantteja asiakirjoja."
        )
        return state

    start_time = time.time()
    logger.info(f"Generating response from {len(results)} chunks...")
    try:
        response = await _generator.agenerate_response(query=state["query"], context_chunks=results)
        state["response"] = response
        elapsed = time.time() - start_time
        logger.info(f"Response ready in {elapsed:.1f}s")

        # Relevancy check: pass compact representation (truncated + citations) to stay within context
        if response and not response.startswith("Pahoittelut"):
            try:
                rel = await check_relevancy(state["query"], response)
                state["relevancy_score"] = float(rel["score"])
                state["relevancy_reason"] = rel.get("reason") or ""
            except Exception as rel_err:
                logger.warning(f"Relevancy check failed: {rel_err}")
                state["relevancy_score"] = None
                state["relevancy_reason"] = None
        else:
            state["relevancy_score"] = None
            state["relevancy_reason"] = None
    except Exception as e:
        logger.error(f"LLM error: {e}")
        state["error"] = f"LLM generation failed: {e!s}"
        state["response"] = "Pahoittelut, vastauksen luomisessa tapahtui virhe. Yritä uudelleen."
        state["relevancy_score"] = None
        state["relevancy_reason"] = None

    return state


async def generate_response(state: AgentState) -> AgentState:
    """
    Node 4: Return final response (Async)
    """
    state["stage"] = "respond"
    if not state.get("response"):
        state["response"] = "Pahoittelut, vastausta ei voitu luoda. Yritä uudelleen."
    return state


async def handle_error(state: AgentState) -> AgentState:
    """
    Error handler node (Async)
    """
    state["stage"] = "error"
    state["response"] = f"❌ Error: {state.get('error', 'Unknown error occurred')}"
    return state
