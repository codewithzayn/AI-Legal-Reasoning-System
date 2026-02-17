"""
© 2026 Crest Advisory Group LLC. All rights reserved.

PROPRIETARY AND CONFIDENTIAL

This file is part of the Crest Pet System and contains proprietary
and confidential information of Crest Advisory Group LLC.
Unauthorized copying, distribution, or use is strictly prohibited.
"""

"""
Resolve user query using conversation context.

When users give fragmented prompts (e.g. "range 1926 to 2000", "about fraud"),
merge with prior messages to build an effective search query.

Conversation boundary: only use recent messages to avoid stale context
when the user has moved to a new topic.
"""

from src.utils.year_filter import extract_year_range

# Max messages to consider when resolving context (prevents stale merge)
MAX_CONTEXT_MESSAGES = 6

# For Case 2 (topic + year merge): only look at last N messages
# (2 exchanges) so we don't attach year from an old, closed thread
MAX_MESSAGES_FOR_YEAR_MERGE = 4

# Legal topic keywords (fi, en, sv) - if present, query is searchable
_LEGAL_TOPIC_WORDS = (
    "fraud",
    "petos",
    "bedrägeri",
    "theft",
    "varkaus",
    "stöld",
    "embezzlement",
    "kavallus",
    "contract",
    "sopimus",
    "avtal",
    "damages",
    "vahingonkorvaus",
    "skadestånd",
    "consequences",
    "seuraus",
    "följd",
    "penalty",
    "rangaistus",
    "straff",
    "kko",
    "kho",
    "rikos",
    "oikeus",
    "laki",
    "tuomio",
    "rangaistus",
    "case",
    "tapaus",
)


def _has_legal_topic(text: str) -> bool:
    """True if text contains a legal topic keyword."""
    if not text or len(text.strip()) < 2:
        return False
    t = text.strip().lower()
    return any(w in t for w in _LEGAL_TOPIC_WORDS)


def _is_mainly_year_range(text: str) -> bool:
    """True if text is primarily a year range with no legal topic (e.g. 'range from 1926 to 2000')."""
    start, _ = extract_year_range(text)
    if start is None:
        return False
    return not _has_legal_topic(text)


def _last_assistant_looks_like_clarification(chat_history: list[dict]) -> bool:
    """True if the last assistant message is a clarification request (not a full answer)."""
    for i in range(len(chat_history) - 1, -1, -1):
        msg = chat_history[i]
        if msg.get("role") != "assistant":
            continue
        content = (msg.get("content") or "").strip().lower()
        if not content:
            continue
        markers = ("clarif", "which years", "what specific", "could you", "please clarify", "tarkentaa", "förtydliga")
        return any(m in content for m in markers) or (len(content) < 180 and "?" in content)
    return False


def _last_user_message_with_topic(chat_history: list[dict]) -> str | None:
    """Return the most recent user message that contains a legal topic."""
    for i in range(len(chat_history) - 1, -1, -1):
        msg = chat_history[i]
        if msg.get("role") != "user":
            continue
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if extract_year_range(content)[0] is not None and _is_mainly_year_range(content):
            continue
        if _has_legal_topic(content):
            return content
    return None


def resolve_query_with_context(
    prompt: str,
    chat_history: list[dict],
) -> tuple[str, tuple[int | None, int | None] | None]:
    """
    Resolve the effective query and optional year range using conversation context.

    Uses only recent messages (MAX_CONTEXT_MESSAGES) to avoid merging from stale threads.
    When the last assistant was a full answer (not clarification), we are stricter
    about merging to avoid attaching context from a previous, closed exchange.

    Returns:
        (effective_query, year_range_or_none)
        - year_range is (start, end) or None; when None, use what's in the query.
    """
    if not prompt or not prompt.strip():
        return (prompt or "", None)

    text = prompt.strip()
    year_from_prompt = extract_year_range(text)

    if not chat_history:
        return (text, None)

    recent = chat_history[-MAX_CONTEXT_MESSAGES:]
    in_clarification_chain = _last_assistant_looks_like_clarification(recent)

    # Case 1: Current prompt is mainly a year range -> use prior topic + this year
    if year_from_prompt[0] is not None and _is_mainly_year_range(text):
        prior = _last_user_message_with_topic(recent)
        if prior:
            return (prior, year_from_prompt)
        return (text, year_from_prompt)

    # Case 2: Current prompt is short and has legal topic; prior user may have given year.
    # Use narrower window when not in clarification chain to avoid stale merge.
    if len(text) < 60 and _has_legal_topic(text) and len(recent) >= 2:
        search_window = recent if in_clarification_chain else recent[-MAX_MESSAGES_FOR_YEAR_MERGE:]
        for i in range(len(search_window) - 1, -1, -1):
            msg = search_window[i]
            if msg.get("role") != "user":
                continue
            content = (msg.get("content") or "").strip()
            y = extract_year_range(content)
            if y[0] is not None and _is_mainly_year_range(content):
                return (text, y)
            if _has_legal_topic(content):
                break

    return (text, None)


def get_recent_context_for_llm(chat_history: list[dict], max_turns: int = 2) -> str:
    """
    Build a short context string from recent conversation for the LLM.

    Used when generating a response so the model understands prior exchanges.
    Returns empty string if no relevant history.
    """
    if not chat_history or max_turns <= 0:
        return ""
    recent = chat_history[-(max_turns * 2) :]
    parts = []
    for msg in recent:
        role = msg.get("role", "")
        content = (msg.get("content") or "").strip()
        if content and len(content) > 500:
            content = content[:500] + "..."
        if not content:
            continue
        if role == "user":
            parts.append(f"User: {content}")
        elif role == "assistant":
            parts.append(f"Assistant: {content}")
    if not parts:
        return ""
    return "Previous conversation:\n" + "\n".join(parts) + "\n\n"
