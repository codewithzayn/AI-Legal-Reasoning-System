"""
EUR-Lex CELLAR SPARQL + REST Client

Fetches EU case law metadata via SPARQL queries against the CELLAR endpoint
and full-text HTML via the EUR-Lex REST API.
"""

import re

import httpx
from SPARQLWrapper import JSON, SPARQLWrapper

from src.config.logging_config import setup_logger
from src.config.settings import config

_SAFE_SPARQL_VALUE_RE = re.compile(r"^[A-Za-z0-9:/_\-. ]+$")


def _sanitise_sparql_literal(value: str) -> str:
    """Escape a string for safe embedding in a SPARQL string literal.

    Rejects values containing characters that could break out of a
    quoted SPARQL string (double-quotes, backslashes, angle brackets,
    curly braces, semicolons, newlines).
    """
    if _SAFE_SPARQL_VALUE_RE.match(value):
        return value
    raise ValueError(f"Unsafe SPARQL literal rejected: {value!r}")


logger = setup_logger(__name__)

# CDM ontology SPARQL prefix block
_SPARQL_PREFIXES = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""


class EurLexClient:
    """Client for EUR-Lex CELLAR SPARQL endpoint and REST API."""

    def __init__(
        self,
        sparql_endpoint: str | None = None,
        rest_endpoint: str | None = None,
    ):
        self.sparql_endpoint = sparql_endpoint or config.EURLEX_SPARQL_ENDPOINT
        self.rest_endpoint = rest_endpoint or config.EURLEX_REST_ENDPOINT
        self._sparql = SPARQLWrapper(self.sparql_endpoint)
        self._sparql.setReturnFormat(JSON)

    def _run_sparql(self, query: str) -> list[dict]:
        """Execute a SPARQL query and return bindings as list[dict]."""
        self._sparql.setQuery(query)
        try:
            results = self._sparql.query().convert()
            bindings = results.get("results", {}).get("bindings", [])
            return [{k: v.get("value", "") for k, v in row.items()} for row in bindings]
        except Exception as e:
            logger.error("SPARQL query failed: %s", e)
            return []

    async def search_cases(
        self,
        court: str = "cjeu",
        year: int | None = None,
        referring_country: str | None = None,
        celex_numbers: list[str] | None = None,
        language: str = "EN",
        limit: int = 100,
    ) -> list[dict]:
        """Search for EU case law via SPARQL.

        Args:
            court: 'cjeu' or 'general_court'
            year: Filter by year of judgment
            referring_country: ISO country code for preliminary references (e.g. 'FIN')
            celex_numbers: Specific CELEX numbers to look up
            language: Language code (EN, FI, etc.)
            limit: Max results

        Returns:
            List of dicts with keys: celex, title, date, ecli, case_number, court_type
        """
        if celex_numbers:
            return self._search_by_celex(celex_numbers, language)

        court_filter = self._court_filter(court)
        year_filter = f"FILTER(YEAR(?date) = {int(year)})" if year else ""
        country_filter = (
            f'FILTER(CONTAINS(STR(?referring_ms), "{_sanitise_sparql_literal(referring_country)}"))'
            if referring_country
            else ""
        )

        query = f"""{_SPARQL_PREFIXES}
SELECT DISTINCT ?celex ?title ?date ?ecli ?case_number WHERE {{
  ?work cdm:resource_legal_id_celex ?celex .
  ?work cdm:work_date_document ?date .
  {court_filter}
  OPTIONAL {{ ?work cdm:case-law_ecli ?ecli . }}
  OPTIONAL {{ ?work cdm:resource_legal_number_natural ?case_number . }}
  OPTIONAL {{ ?work cdm:work_has_expression ?expr .
              ?expr cdm:expression_title ?title .
              ?expr cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/{language}> . }}
  {year_filter}
  {country_filter}
}}
ORDER BY DESC(?date)
LIMIT {limit}
"""
        rows = self._run_sparql(query)
        for row in rows:
            row["court_type"] = court
        logger.info("EUR-Lex search → %s results (court=%s, year=%s)", len(rows), court, year)
        return rows

    def _search_by_celex(self, celex_numbers: list[str], language: str) -> list[dict]:
        """Fetch metadata for specific CELEX numbers."""
        filter_expr = " || ".join(f'STR(?celex) = "{_sanitise_sparql_literal(c)}"' for c in celex_numbers)
        query = f"""{_SPARQL_PREFIXES}
SELECT DISTINCT ?celex ?title ?date ?ecli ?case_number WHERE {{
  ?work cdm:resource_legal_id_celex ?celex .
  FILTER({filter_expr})
  OPTIONAL {{ ?work cdm:work_date_document ?date . }}
  OPTIONAL {{ ?work cdm:case-law_ecli ?ecli . }}
  OPTIONAL {{ ?work cdm:resource_legal_number_natural ?case_number . }}
  OPTIONAL {{ ?work cdm:work_has_expression ?expr .
              ?expr cdm:expression_title ?title .
              ?expr cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/{language}> . }}
}}
"""
        return self._run_sparql(query)

    @staticmethod
    def _court_filter(court: str) -> str:
        """SPARQL filter clause for court type."""
        if court == "cjeu":
            return "?work cdm:case-law_delivered_by_court <http://publications.europa.eu/resource/authority/court/CJ> ."
        if court == "general_court":
            return "?work cdm:case-law_delivered_by_court <http://publications.europa.eu/resource/authority/court/GC> ."
        return ""

    async def fetch_case_text(self, celex_number: str, language: str = "EN") -> str:
        """Fetch the full text of a case via CELLAR content negotiation.

        Uses the publications.europa.eu CELLAR endpoint which serves XHTML
        without the WAF challenges that eur-lex.europa.eu uses.

        Args:
            celex_number: CELEX identifier (e.g. '62018CJ0311')
            language: Language code (EN, FI)

        Returns:
            Plain text extracted from XHTML, or empty string on failure.
        """
        lang_map = {"EN": "eng", "FI": "fin", "SV": "swe", "DE": "deu", "FR": "fra"}
        accept_lang = lang_map.get(language, language.lower())

        try:
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                # Step 1: Get cellar UUID from notice XML
                notice_url = f"https://publications.europa.eu/resource/celex/{celex_number}"
                resp = await client.get(
                    notice_url,
                    headers={"Accept": "application/xml;notice=object"},
                )
                resp.raise_for_status()

                from lxml import etree

                root = etree.fromstring(resp.content)
                cellar_id = root.findtext(".//{*}WORK/{*}URI/{*}IDENTIFIER", "")
                if not cellar_id:
                    raise ValueError("No cellar ID in notice XML")

                # Step 2: Fetch XHTML from cellar URI
                cellar_url = f"https://publications.europa.eu/resource/cellar/{cellar_id}"
                resp = await client.get(
                    cellar_url,
                    headers={
                        "Accept": "application/xhtml+xml",
                        "Accept-Language": accept_lang,
                    },
                )
                resp.raise_for_status()

                # Parse XHTML (use bytes to handle encoding declarations)
                doc = etree.fromstring(resp.content, etree.HTMLParser(encoding="utf-8"))
                text = "".join(doc.itertext())
                text = re.sub(r"\n{3,}", "\n\n", text).strip()

            logger.info("Fetched %s chars for CELEX %s (%s)", len(text), celex_number, language)
            return text
        except Exception as e:
            logger.error("Failed to fetch text for CELEX %s (%s): %s", celex_number, language, e)
            return ""

    async def fetch_case_metadata(self, celex_number: str) -> dict:
        """Fetch detailed metadata for a single CELEX number.

        Returns dict with: celex, title, date, ecli, case_number,
        advocate_general, formation, subject_matter, referring_court, referring_country.
        """
        query = f"""{_SPARQL_PREFIXES}
SELECT ?celex ?title ?date ?ecli ?case_number
       ?ag ?formation ?subject ?ref_court ?ref_country WHERE {{
  ?work cdm:resource_legal_id_celex ?celex .
  FILTER(STR(?celex) = "{_sanitise_sparql_literal(celex_number)}")
  OPTIONAL {{ ?work cdm:work_date_document ?date . }}
  OPTIONAL {{ ?work cdm:case-law_ecli ?ecli . }}
  OPTIONAL {{ ?work cdm:resource_legal_number_natural ?case_number . }}
  OPTIONAL {{ ?work cdm:work_has_expression ?expr .
              ?expr cdm:expression_title ?title .
              ?expr cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/EN> . }}
  OPTIONAL {{ ?work cdm:case-law_advocate-general_name ?ag . }}
  OPTIONAL {{ ?work cdm:case-law_delivered_by_court_formation ?formation . }}
  OPTIONAL {{ ?work cdm:case-law_is_about_subject-matter ?subject . }}
  OPTIONAL {{ ?work cdm:case-law_preliminary_ruling_referring_court ?ref_court . }}
  OPTIONAL {{ ?work cdm:case-law_preliminary_ruling_referring_ms ?ref_country . }}
}}
LIMIT 1
"""
        rows = self._run_sparql(query)
        if not rows:
            return {}
        row = rows[0]
        return {
            "celex": row.get("celex", celex_number),
            "title": row.get("title", ""),
            "date": row.get("date", ""),
            "ecli": row.get("ecli", ""),
            "case_number": row.get("case_number", ""),
            "advocate_general": row.get("ag", ""),
            "formation": row.get("formation", ""),
            "subject_matter": row.get("subject", ""),
            "referring_court": row.get("ref_court", ""),
            "referring_country": row.get("ref_country", ""),
        }

    async def find_finnish_preliminary_references(self, year_start: int = 1995, year_end: int = 2026) -> list[dict]:
        """Find all CJEU preliminary rulings referred by Finnish courts.

        Uses the CDM property for referring member state filtered to Finland.
        """
        query = f"""{_SPARQL_PREFIXES}
SELECT DISTINCT ?celex ?title ?date ?ecli ?case_number ?ref_court WHERE {{
  ?work cdm:resource_legal_id_celex ?celex .
  ?work cdm:work_date_document ?date .
  ?work cdm:case-law_preliminary_ruling_referring_ms ?ref_ms .
  FILTER(CONTAINS(STR(?ref_ms), "FIN"))
  FILTER(YEAR(?date) >= {int(year_start)} && YEAR(?date) <= {int(year_end)})
  OPTIONAL {{ ?work cdm:case-law_ecli ?ecli . }}
  OPTIONAL {{ ?work cdm:resource_legal_number_natural ?case_number . }}
  OPTIONAL {{ ?work cdm:case-law_preliminary_ruling_referring_court ?ref_court . }}
  OPTIONAL {{ ?work cdm:work_has_expression ?expr .
              ?expr cdm:expression_title ?title .
              ?expr cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/EN> . }}
}}
ORDER BY DESC(?date)
"""
        rows = self._run_sparql(query)
        for row in rows:
            row["court_type"] = "cjeu"
            row["referring_country"] = "Finland"
        logger.info("Finnish preliminary references → %s results (%s-%s)", len(rows), year_start, year_end)
        return rows
