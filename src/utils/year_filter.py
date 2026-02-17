"""
© 2026 Crest Advisory Group LLC. All rights reserved.

PROPRIETARY AND CONFIDENTIAL

This file is part of the Crest Pet System and contains proprietary
and confidential information of Crest Advisory Group LLC.
Unauthorized copying, distribution, or use is strictly prohibited.
"""

"""
Year range extraction for case-law search filtering.

Parses user queries and clarification responses for year ranges
(e.g. "2010-2020", "from 1926 to 1927", "cases from 2015").
"""

import re

# Patterns for year range in query
_YEAR_RANGE_PATTERNS = [
    # "from 2010 to 2020", "from 1926 to 1927"
    re.compile(r"from\s+(\d{4})\s+to\s+(\d{4})", re.IGNORECASE),
    # "2010-2020", "1926-1927", "2010–2020" (en dash)
    re.compile(r"(\d{4})\s*[-–]\s*(\d{4})"),
    # "between 2010 and 2020"
    re.compile(r"between\s+(\d{4})\s+and\s+(\d{4})", re.IGNORECASE),
    # "years 2010 to 2020"
    re.compile(r"years?\s+(\d{4})\s+to\s+(\d{4})", re.IGNORECASE),
    # "range 1926 to 2000", "1926 to 2000"
    re.compile(r"(\d{4})\s+to\s+(\d{4})"),
    # Single year: "2015", "from 2015", "year 2015", "in 2026"
    re.compile(r"(?:^|from|year|in)\s+(\d{4})\b", re.IGNORECASE),
    # Bare year only (e.g. user reply "1926" or "2026" to year clarification)
    re.compile(r"^(\d{4})$"),
]


def extract_year_range(query: str) -> tuple[int | None, int | None]:
    """Extract year range from a query string.

    Returns (year_start, year_end). Both inclusive.
    If single year found, returns (year, year).
    If no year found, returns (None, None).
    """
    if not query or not query.strip():
        return (None, None)

    text = query.strip()
    # Try range patterns first
    for pat in _YEAR_RANGE_PATTERNS[:5]:
        m = pat.search(text)
        if m:
            y1, y2 = int(m.group(1)), int(m.group(2))
            if y1 <= y2:
                return (y1, y2)
            return (y2, y1)

    # Single year (prefixed or bare)
    for pat in _YEAR_RANGE_PATTERNS[5:]:
        m = pat.search(text)
        if m:
            y = int(m.group(1))
            if 1900 <= y <= 2100:
                return (y, y)

    return (None, None)


def parse_year_response(response: str) -> tuple[int | None, int | None] | None:
    """Parse a user's reply to the year clarification question.

    Returns (year_start, year_end) if valid, or None if user said "all" / no filter.
    """
    if not response:
        return None
    text = response.strip().lower()
    # "all", "any", "no filter", "ei rajoitusta" etc.
    if text in ("all", "any", "no filter", "none", "kaikki", "ei rajoitusta", "ingen begränsning"):
        return None
    return extract_year_range(response) if extract_year_range(response)[0] else None


def has_year_in_query(query: str) -> bool:
    """Return True if the query explicitly mentions a year or year range."""
    start, _ = extract_year_range(query)
    return start is not None
