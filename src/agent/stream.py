"""
Streaming version of agent for Streamlit
"""

from collections.abc import AsyncIterator

from src.config.logging_config import setup_logger

from .graph import agent_graph
from .state import AgentState

logger = setup_logger(__name__)


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
        "relevancy_score": None,
        "relevancy_reason": None,
        "error": None,
    }

    # Stream events from the graph
    # We yield status messages for intermediate steps
    try:
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

                elif stage == "chat":
                    # Yield the chat response
                    response = value.get("response", "")
                    yield response

                elif stage == "respond":
                    # Yield the final answer
                    response = value.get("response", "")
                    yield response
                    # Relevancy score (compact check ran on truncated answer + citations)
                    score = value.get("relevancy_score")
                    reason = value.get("relevancy_reason")
                    if score is not None and reason:
                        yield f"\n\n---\n⚖️ Relevanssi: {int(score)}/5. {reason}"
                    elif score is not None:
                        yield f"\n\n---\n⚖️ Relevanssi: {int(score)}/5."

                elif stage == "error":
                    yield f"❌ Virhe: {value.get('error')}"
    except Exception as e:
        logger.error(f"Stream error: {e}")
        yield f"⚠️ Virhe yhteydessä: {e!s}"
    finally:
        # Give a small window for background tasks (like LangSmith tracers) to finish
        import asyncio

        await asyncio.sleep(0.2)
        logger.debug("Stream finished.")
