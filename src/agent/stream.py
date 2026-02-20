"""
Streaming version of agent for Streamlit
"""

import asyncio
import contextlib
import queue
import threading
from collections.abc import AsyncIterator, Iterator

from src.config.logging_config import setup_logger
from src.config.settings import config
from src.config.translations import t
from src.utils.lang_detect import detect_query_language

from .graph import agent_graph
from .state import AgentState

logger = setup_logger(__name__)


def _strip_relevancy_line(text: str) -> str:
    """Remove any trailing relevancy score line so it is never shown to the user."""
    if not text:
        return text
    lines = text.split("\n")
    out = []
    for line in lines:
        if ("Relevanssi:" in line or "Relevancy:" in line) and ("/5" in line or "5/5" in line):
            continue
        out.append(line)
    return "\n".join(out).rstrip()


def _resolve_query_params(
    user_query: str,
    original_query_for_year: str | None,
    year_range: tuple[int | None, int | None] | None,
) -> tuple[str, int | None, int | None, bool]:
    """Resolve effective query, year filter, and year_clarification_answered."""
    if original_query_for_year and year_range is not None:
        return original_query_for_year, year_range[0], year_range[1], True
    return user_query, None, None, False


def _resolve_response_lang(user_query: str, lang: str, effective_query: str) -> str:
    """Resolve response language from UI lang (or auto-detect)."""
    if lang in ("en", "fi", "sv"):
        return lang
    if lang == "auto":
        detect_source = user_query if len(user_query.strip()) > 5 else effective_query
        return detect_query_language(detect_source) if detect_source.strip() else "fi"
    return "fi"


def _update_metadata_sink(sink: dict | None, value: dict) -> None:
    """Copy selected graph-update keys into the metadata sink dict."""
    if sink is None or not isinstance(value, dict):
        return
    if "search_results" in value:
        sink["search_results"] = value["search_results"]
    if value.get("relevancy_score") is not None:
        sink["relevancy_score"] = value["relevancy_score"]
    if value.get("relevancy_reason") is not None:
        sink["relevancy_reason"] = value["relevancy_reason"]
    if "retrieval_metadata" in value:
        sink["retrieval_metadata"] = value["retrieval_metadata"]


def _build_initial_state(
    effective_query: str,
    year_start: int | None,
    year_end: int | None,
    year_clarification_answered: bool,
    chat_history: list[dict] | None,
    stream_queue: asyncio.Queue[str | None],
    response_lang: str,
    court_types: list[str] | None = None,
    legal_domains: list[str] | None = None,
    tenant_id: str | None = None,
) -> AgentState:
    """Build initial agent state for the graph."""
    return {
        "query": effective_query,
        "messages": chat_history[-12:] if chat_history else [],
        "stage": "init",
        "search_attempts": 0,
        "original_query": effective_query,
        "intent": "",
        "search_results": [],
        "response": "",
        "relevancy_score": None,
        "relevancy_reason": None,
        "error": None,
        "response_lang": response_lang,
        "year_start": year_start,
        "year_end": year_end,
        "year_clarification_answered": year_clarification_answered,
        "stream_queue": stream_queue,
        "court_types": court_types,
        "legal_domains": legal_domains,
        "tenant_id": tenant_id,
    }


def _yield_for_event(
    key: str,
    value: dict,
    lang: str,
    streamed_response: bool,
) -> tuple[str | None, bool]:
    """
    Process a graph event and return (yield_value, should_break).
    yield_value is None if nothing to yield; should_break is True for _done.
    """
    handlers: dict[str, tuple[str | None, bool]] = {
        "_done": (None, True),
        "analyze": (f"\U0001f914 {t('stream_analyzing', lang)}\n\n", False),
        "search": (f"\U0001f50d {t('stream_searching', lang)}\n\n", False),
        "reformulate": (None, False),
    }
    if key in handlers:
        return handlers[key]
    if key in {"clarify", "clarify_year", "chat"}:
        resp = _strip_relevancy_line(value.get("response", ""))
        return (resp if resp else None), False
    if key == "respond" and not streamed_response:
        resp = _strip_relevancy_line(value.get("response", ""))
        return (resp if resp else None), False
    if key == "error":
        return f"\u274c {t('stream_error', lang, error=value.get('error'))}", False
    return None, False


async def _stream_loop(
    events_queue: asyncio.Queue[tuple[str, dict]],
    stream_queue: asyncio.Queue[str | None],
    lang: str,
) -> AsyncIterator[str]:
    """Main stream loop: wait for events or chunks, yield UI updates and response."""
    streamed_response = False
    while True:
        event_result: list[tuple[str, dict]] = []
        queue_result: list[str | None] = []

        async def get_event(ev_result: list = event_result) -> None:
            key, val = await events_queue.get()
            ev_result.append((key, val))

        async def get_chunk(q_result: list = queue_result) -> None:
            chunk = await stream_queue.get()
            q_result.append(chunk)

        get_event_task = asyncio.create_task(get_event())
        get_chunk_task = asyncio.create_task(get_chunk())

        done, _ = await asyncio.wait(
            [get_event_task, get_chunk_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        if get_chunk_task in done:
            get_event_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await get_event_task
            if event_result:
                await events_queue.put(event_result[0])
            chunk = queue_result[0]
            if chunk is None:
                continue
            streamed_response = True
            yield chunk
        else:
            get_chunk_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await get_chunk_task
            key, value = event_result[0]
            yield_val, should_break = _yield_for_event(key, value, lang, streamed_response)
            if should_break:
                break
            if yield_val:
                yield yield_val


async def stream_query_response(
    user_query: str,
    lang: str = "en",
    original_query_for_year: str | None = None,
    year_range: tuple[int | None, int | None] | None = None,
    chat_history: list[dict] | None = None,
    court_types: list[str] | None = None,
    legal_domains: list[str] | None = None,
    tenant_id: str | None = None,
    metadata_sink: dict | None = None,
) -> AsyncIterator[str]:
    """
    Stream response from agent.

    Args:
        user_query: User's question
        lang: Language code for UI and response ("en", "fi", or "sv")
        original_query_for_year: When continuing from year clarification, the original query
        year_range: (year_start, year_end) from user's year clarification response
        court_types: Optional list of court type filters (e.g. ["KKO", "KHO"])
        legal_domains: Optional list of legal domain filters
        tenant_id: Optional tenant ID for multi-tenant document isolation

    Yields:
        Response chunks as they're generated
    """
    if len(user_query) > config.MAX_QUERY_LENGTH:
        yield f"\u26a0\ufe0f {t('query_too_long', lang, max=config.MAX_QUERY_LENGTH)}"
        return

    effective_query, year_start, year_end, year_clarification_answered = _resolve_query_params(
        user_query, original_query_for_year, year_range
    )

    response_lang = _resolve_response_lang(user_query, lang, effective_query)

    stream_queue: asyncio.Queue[str | None] = asyncio.Queue()
    initial_state = _build_initial_state(
        effective_query,
        year_start,
        year_end,
        year_clarification_answered,
        chat_history,
        stream_queue,
        response_lang,
        court_types=court_types,
        legal_domains=legal_domains,
        tenant_id=tenant_id,
    )

    events_queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()

    async def _run_graph() -> None:
        try:
            async for event in agent_graph.astream(initial_state, stream_mode="updates"):
                payload = event[-1] if isinstance(event, tuple) else event
                if not isinstance(payload, dict):
                    continue
                for key, value in payload.items():
                    _update_metadata_sink(metadata_sink, value if isinstance(value, dict) else {})
                    await events_queue.put((key, value))
            await events_queue.put(("_done", {}))
        except Exception as e:
            logger.error("Graph error: %s", e)
            await events_queue.put(("error", {"error": str(e)}))

    graph_task = asyncio.create_task(_run_graph())

    try:
        async for chunk in _stream_loop(events_queue, stream_queue, lang):
            yield chunk
        await graph_task
    except Exception as e:
        logger.error("Stream error: %s", e)
        yield f"\u26a0\ufe0f {t('stream_connection_error', lang, error=str(e))}"
    finally:
        try:
            if not graph_task.done():
                graph_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await graph_task
            await asyncio.sleep(0.2)
        except RuntimeError:
            pass
        logger.debug("Stream finished.")


def stream_query_response_sync(
    user_query: str,
    lang: str = "en",
    original_query_for_year: str | None = None,
    year_range: tuple[int | None, int | None] | None = None,
    chat_history: list[dict] | None = None,
) -> Iterator[str]:
    """
    Synchronous wrapper for stream_query_response so Streamlit can iterate
    without async. Runs the async generator in a background thread and yields
    chunks on the main thread.
    """
    chunk_queue: queue.Queue[str | None] = queue.Queue()

    def run() -> None:
        loop = asyncio.new_event_loop()
        try:

            async def consume() -> None:
                async for chunk in stream_query_response(
                    user_query,
                    lang=lang,
                    original_query_for_year=original_query_for_year,
                    year_range=year_range,
                    chat_history=chat_history,
                ):
                    chunk_queue.put(chunk)
                chunk_queue.put(None)

            loop.run_until_complete(consume())
        finally:
            loop.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    while True:
        chunk = chunk_queue.get()
        if chunk is None:
            break
        yield chunk
    thread.join(timeout=1.0)
