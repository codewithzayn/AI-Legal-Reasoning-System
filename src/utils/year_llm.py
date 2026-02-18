"""
© 2026 Crest Advisory Group LLC. All rights reserved.

PROPRIETARY AND CONFIDENTIAL

This file is part of the Crest Pet System and contains proprietary
and confidential information of Crest Advisory Group LLC.
Unauthorized copying, distribution, or use is strictly prohibited.
"""

"""
LLM-based year scope interpretation.

Uses the AI to understand user intent for year filtering instead of hardcoded phrases.
Covers: "for all years", "check all", "any year", and variations in any language.
"""

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.config.logging_config import setup_logger
from src.utils.retry import retry_async, with_retry
from src.utils.year_filter import extract_year_range

logger = setup_logger(__name__)

_llm_mini = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Year scope: "ask" = clarify, "all" = no filter, "specific" = use extracted range
_YEAR_SCOPE_SYSTEM = """You interpret the user's intent regarding which years of court decisions to search.

Given a legal search query, determine the year scope:

1. "all" - User explicitly wants ALL years / no filter. Examples: "for all years", "all years", "any year", "check all", "every year", "no restriction", "no filter", "any time", "don't care about years", "search everything".
2. "specific" - User specified a year or range (e.g. 2018, 2010-2020, "from 2015").
3. "ask" - User has NOT specified; we should ask which years to search.

Respond with exactly one word on the first line: all, specific, or ask.
If "specific", add a second line with the year/range as YEAR or YEAR1-YEAR2 (e.g. 2018 or 2010-2020). Use 4-digit years."""

_YEAR_REPLY_SYSTEM = """The user was asked: "Which years' court decisions would you like to search? Specify a range (e.g. 2010–2020) or say 'all' for no filter."

Interpret their reply. Respond with exactly one word on the first line:
- "all" - They want no filter / all years. Examples: "all", "check all", "every year", "any", "no filter", "any year", "I don't care", "all of them".
- "specific" - They gave a year or range (e.g. "2018", "2010-2020", "from 2015 to 2020").
- "ask" - Unclear; treat as needing clarification.

If "specific", add a second line with the year or range as YEAR or YEAR1-YEAR2."""


def _parse_year_from_llm_line(line: str) -> tuple[int | None, int | None]:
    """Parse YEAR or YEAR1-YEAR2 from LLM output line. Falls back to extract_year_range."""
    line = (line or "").strip()
    if not line:
        return (None, None)
    # Try "2010-2020" or "2010 - 2020"
    if "-" in line:
        parts = line.replace(" ", "").split("-")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            y1, y2 = int(parts[0]), int(parts[1])
            if 1900 <= y1 <= 2100 and 1900 <= y2 <= 2100:
                return (min(y1, y2), max(y1, y2))
    # Single year
    if line.isdigit() and len(line) == 4:
        y = int(line)
        if 1900 <= y <= 2100:
            return (y, y)
    # Fallback to regex
    return extract_year_range(line)


@with_retry(retries=2)
def interpret_year_reply_sync(reply: str) -> tuple[int | None, int | None] | None:
    """
    Interpret user's reply to year clarification using LLM (sync).

    Returns (year_start, year_end) for specific range, or None for "all" / no filter.
    Used when user replies "check all", "all", "2018", etc. to the year question.
    """
    if not reply or not reply.strip():
        return None
    try:
        response = _llm_mini.invoke([SystemMessage(content=_YEAR_REPLY_SYSTEM), HumanMessage(content=reply.strip())])
        text = (response.content or "").strip().lower()
        lines = [ln.strip().lower() for ln in text.splitlines() if ln.strip()]
        first = lines[0] if lines else ""
        if first == "all":
            return None
        if first == "specific" and len(lines) >= 2:
            y1, y2 = _parse_year_from_llm_line(lines[1])
            if y1 is not None:
                return (y1, y2)
        if first == "ask":
            return None
        # Fallback: try regex extraction
        y1, y2 = extract_year_range(reply)
        if y1 is not None:
            return (y1, y2)
        return None
    except Exception as e:
        logger.warning("Year reply interpretation failed, using fallback: %s", e)
        y1, _ = extract_year_range(reply)
        return (y1, y1) if y1 is not None else None


async def interpret_year_scope_from_query_async(query: str) -> tuple[str, int | None, int | None]:
    """
    Interpret year scope from user's initial query using LLM (async).

    Returns ("ask"|"all"|"specific", year_start, year_end).
    - "all": search all years, no filter
    - "specific": use year_start, year_end
    - "ask": ask user which years to search
    """
    if not query or not query.strip():
        return ("ask", None, None)
    try:
        response = await retry_async(
            lambda: _llm_mini.ainvoke([SystemMessage(content=_YEAR_SCOPE_SYSTEM), HumanMessage(content=query.strip())])
        )
        text = (response.content or "").strip().lower()
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        first = (lines[0] if lines else "").strip().lower()
        if first == "all":
            return ("all", None, None)
        if first == "specific" and len(lines) >= 2:
            y1, y2 = _parse_year_from_llm_line(lines[1])
            if y1 is not None:
                return ("specific", y1, y2)
        if first == "specific":
            y1, y2 = extract_year_range(query)
            if y1 is not None:
                return ("specific", y1, y2)
        return ("ask", None, None)
    except Exception as e:
        logger.warning("Year scope interpretation failed, falling back to ask: %s", e)
        y1, y2 = extract_year_range(query)
        if y1 is not None:
            return ("specific", y1, y2)
        return ("ask", None, None)
