"""
Streaming version of agent for Streamlit
"""

from collections.abc import AsyncIterator

from src.config.logging_config import setup_logger

from .graph import agent_graph
from .state import AgentState

logger = setup_logger(__name__)


def _strip_relevancy_line(text: str) -> str:
    """Remove any trailing relevancy score line so it is never shown to the user."""
    if not text or "Relevanssi:" not in text:
        return text
    lines = text.split("\n")
    out = []
    for line in lines:
        if "Relevanssi:" in line and ("/5" in line or "5/5" in line):
            continue
        out.append(line)
    return "\n".join(out).rstrip()


async def stream_query_response(user_query: str) -> AsyncIterator[str]:
    """
    Stream response from agent.
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

    try:
        async for event in agent_graph.astream(initial_state):
            for key, value in event.items():
                if key == "analyze":
                    yield "🤔 Analysoidaan kysymystä...\n\n"

                elif key == "search":
                    count = len(value.get("search_results", []))
                    yield f"🔍 Etsitään tietoa... (Löydetty {count} tulosta)\n\n"

                elif key == "reformulate":
                    new_query = value.get("query", "")
                    yield f"🔄 Hakutuloksia ei löytynyt. Tarkennetaan hakua: '{new_query}'...\n\n"

                elif key in {"clarify", "chat"}:
                    yield value.get("response", "")

                elif key == "respond":
                    resp = value.get("response", "")
                    yield _strip_relevancy_line(resp)

                elif key == "error":
                    yield f"❌ Virhe: {value.get('error')}"
    except Exception as e:
        logger.error("Stream error: %s", e)
        yield f"⚠️ Virhe yhteydessä: {e!s}"
    finally:
        import asyncio

        await asyncio.sleep(0.2)
        logger.debug("Stream finished.")
