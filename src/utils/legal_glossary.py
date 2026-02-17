"""
© 2026 Crest Advisory Group LLC. All rights reserved.

PROPRIETARY AND CONFIDENTIAL

This file is part of the Crest Pet System and contains proprietary
and confidential information of Crest Advisory Group LLC.
Unauthorized copying, distribution, or use is strictly prohibited.
"""

"""
Multilingual legal glossary for query expansion.

Maps legal terms across Finnish, English, and Swedish to improve
cross-lingual retrieval when users query in English or Swedish
against mostly Finnish case-law content.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

# Path to glossary relative to project root
_GLOSSARY_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "legal_glossary.json"


@lru_cache(maxsize=1)
def _load_glossary() -> dict[str, dict[str, str]]:
    """Load glossary and build lookup index for en/sv -> fi expansion."""
    index: dict[str, dict[str, str]] = {"en": {}, "sv": {}}
    if not _GLOSSARY_PATH.exists():
        return index

    try:
        with open(_GLOSSARY_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return index

    terms = data.get("terms") or []
    for entry in terms:
        fi_term = (entry.get("fi") or "").strip()
        en_term = (entry.get("en") or "").strip()
        sv_term = (entry.get("sv") or "").strip()
        if not fi_term:
            continue
        if en_term:
            index["en"][en_term.lower()] = fi_term
        if sv_term:
            index["sv"][sv_term.lower()] = fi_term

    return index


def expand_query_with_glossary(query: str, source_lang: str | None) -> str:
    """Expand query with Finnish equivalents when source language is en or sv.

    When the user queries in English or Swedish, adds Finnish legal terms
    from the glossary to improve recall against Finnish case-law content.
    Returns the original query with any matched Finnish terms appended.

    Args:
        query: Original user query.
        source_lang: Detected or selected language ("en", "sv", "fi", or None).

    Returns:
        Query string, possibly with Finnish terms appended.
    """
    if not query or not source_lang:
        return query
    lang = source_lang.lower()
    if lang not in ("en", "sv"):
        return query

    index = _load_glossary()
    lookup = index.get(lang, {})
    if not lookup:
        return query

    # Tokenize: split on whitespace, strip punctuation, keep words >= 3 chars
    def _normalize(w: str) -> str:
        return re.sub(r"[^\w]", "", w.strip().lower())

    words = [_normalize(w) for w in query.split() if len(w.strip()) >= 3]
    word_set = set(words)
    added: set[str] = set()
    for word in words:
        fi_term = lookup.get(word)
        if fi_term and _normalize(fi_term) not in word_set:
            added.add(fi_term)

    if not added:
        return query
    return f"{query} {' '.join(sorted(added))}"


def get_glossary_stats() -> dict[str, int]:
    """Return counts of glossary entries per target language (for debugging)."""
    idx = _load_glossary()
    return {"en": len(idx.get("en", {})), "sv": len(idx.get("sv", {}))}
