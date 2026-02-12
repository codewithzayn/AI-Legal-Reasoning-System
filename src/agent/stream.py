"""
Streaming version of agent for Streamlit
"""

from collections.abc import AsyncIterator

from src.config.logging_config import setup_logger
from src.config.settings import config
from src.config.translations import t

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


async def stream_query_response(user_query: str, lang: str = "en") -> AsyncIterator[str]:
    """
    Stream response from agent.

    Args:
        user_query: User's question
        lang: Language code for UI messages ("en" or "fi")

    Yields:
        Response chunks as they're generated
    """
    if len(user_query) > config.MAX_QUERY_LENGTH:
        yield f"\u26a0\ufe0f {t('query_too_long', lang, max=config.MAX_QUERY_LENGTH)}"
        return

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
        async for event in agent_graph.astream(initial_state, stream_mode="updates"):
            payload = event[-1] if isinstance(event, tuple) else event
            if not isinstance(payload, dict):
                continue
            for key, value in payload.items():
                if key == "analyze":
                    yield f"\U0001f914 {t('stream_analyzing', lang)}\n\n"

                elif key == "search":
                    count = len(value.get("search_results", []))
                    yield f"\U0001f50d {t('stream_searching', lang, count=count)}\n\n"

                elif key == "reformulate":
                    new_query = value.get("query", "")
                    yield f"\U0001f504 {t('stream_reformulating', lang, query=new_query)}\n\n"

                elif key in {"clarify", "chat", "respond"}:
                    resp = _strip_relevancy_line(value.get("response", ""))
                    if resp:
                        yield resp

                elif key == "error":
                    yield f"\u274c {t('stream_error', lang, error=value.get('error'))}"
    except Exception as e:
        logger.error("Stream error: %s", e)
        yield f"\u26a0\ufe0f {t('stream_connection_error', lang, error=str(e))}"
    finally:
        import asyncio

        await asyncio.sleep(0.2)
        logger.debug("Stream finished.")
