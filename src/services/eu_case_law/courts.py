"""
EU Court Registry — court type mapping, case ID parsing, and URL building.
"""

import re

# DB court_type → display name
EU_COURT_TYPES: dict[str, str] = {
    "cjeu": "Court of Justice of the EU",
    "general_court": "General Court",
    "echr": "European Court of Human Rights",
}

# DB court_type → short code (for UI badges / logs)
EU_COURT_CODES: dict[str, str] = {
    "cjeu": "CJEU",
    "general_court": "GC",
    "echr": "ECHR",
}

# ECLI prefix → DB court_type
ECLI_PREFIXES: dict[str, str] = {
    "ECLI:EU:C:": "cjeu",
    "ECLI:EU:T:": "general_court",
}

# Regex patterns for EU case IDs
_CJEU_CASE_RE = re.compile(r"\bC-(\d+)/(\d{2,4})\b")
_GC_CASE_RE = re.compile(r"\bT-(\d+)/(\d{2,4})\b")
_ECLI_EU_RE = re.compile(r"\bECLI:EU:[CT]:\d{4}:\d+\b")
_ECHR_APP_RE = re.compile(r"\bapplication\s+no\.?\s*(\d+/\d{2,4})\b", re.IGNORECASE)
_ECHR_APP_SHORT_RE = re.compile(r"\b(\d{4,6}/\d{2,4})\b")


def parse_eu_case_id(raw_id: str) -> dict | None:
    """Parse a raw EU case identifier into structured components.

    Returns dict with keys: court_type, case_number, ecli (if applicable).
    Returns None if the string doesn't match any EU case ID pattern.
    """
    raw = raw_id.strip()

    # ECLI
    ecli_match = _ECLI_EU_RE.search(raw)
    if ecli_match:
        ecli = ecli_match.group(0)
        for prefix, court_type in ECLI_PREFIXES.items():
            if ecli.startswith(prefix):
                return {"court_type": court_type, "case_number": ecli, "ecli": ecli}

    # CJEU: C-311/18
    m = _CJEU_CASE_RE.search(raw)
    if m:
        return {
            "court_type": "cjeu",
            "case_number": f"C-{m.group(1)}/{m.group(2)}",
            "ecli": None,
        }

    # General Court: T-123/20
    m = _GC_CASE_RE.search(raw)
    if m:
        return {
            "court_type": "general_court",
            "case_number": f"T-{m.group(1)}/{m.group(2)}",
            "ecli": None,
        }

    # ECHR application number
    m = _ECHR_APP_RE.search(raw)
    if m:
        return {
            "court_type": "echr",
            "case_number": m.group(1),
            "ecli": None,
        }

    return None


def build_eu_case_url(court_type: str, case_id: str | None = None, celex: str | None = None) -> str:
    """Build a canonical URL for an EU case.

    For CJEU/GC: EUR-Lex URL using CELEX number, or CURIA search URL.
    For ECHR: HUDOC URL.
    """
    if court_type in ("cjeu", "general_court"):
        if celex:
            return f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}"
        if case_id:
            # CURIA search fallback
            return f"https://curia.europa.eu/juris/liste.jsf?num={case_id}&language=en"
        return ""

    if court_type == "echr":
        if case_id:
            return f"https://hudoc.echr.coe.int/eng?i={case_id}"
        return ""

    return ""
