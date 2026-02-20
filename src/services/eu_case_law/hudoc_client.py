"""
HUDOC API Client — European Court of Human Rights case law.

Fetches ECHR cases and full-text judgments from the HUDOC query API.
"""

import re

import httpx

from src.config.logging_config import setup_logger
from src.config.settings import config

logger = setup_logger(__name__)


class HudocClient:
    """Client for the ECHR HUDOC JSON query API."""

    def __init__(self, api_url: str | None = None):
        self.api_url = api_url or config.HUDOC_API_URL

    async def search_cases(
        self,
        respondent_state: str | None = None,
        year: int | None = None,
        importance_level: str | None = None,
        language: str = "ENG",
        limit: int = 100,
    ) -> list[dict]:
        """Search ECHR cases via HUDOC API.

        Args:
            respondent_state: Filter by respondent state (e.g. 'FIN')
            year: Filter by judgment year
            importance_level: '1' (key), '2' (important), '3' (other)
            language: Language code (ENG, FRE)
            limit: Max results

        Returns:
            List of dicts with: item_id, title, date, app_no, importance,
            respondent, conclusion, ecli
        """
        query_parts = [
            'contentsitename:"ECHR"',
            'documentcollectionid2:"JUDGMENTS"',
        ]
        if respondent_state:
            query_parts.append(f'respondent:"{respondent_state}"')
        if year:
            query_parts.append(f'kpdate:"{year}"')
        if importance_level:
            query_parts.append(f'importance:"{importance_level}"')

        params = {
            "query": " AND ".join(query_parts),
            "select": "itemid,docname,kpdate,appno,importance,respondent,conclusion,ecli",
            "sort": "kpdate Descending",
            "start": 0,
            "length": limit,
            "language": language,
        }

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(self.api_url, params=params)
                resp.raise_for_status()
                data = resp.json()

            results = data.get("results", [])
            cases = []
            for item in results:
                columns = item.get("columns", {})
                cases.append(
                    {
                        "item_id": columns.get("itemid", ""),
                        "title": columns.get("docname", ""),
                        "date": columns.get("kpdate", ""),
                        "app_no": columns.get("appno", ""),
                        "importance": columns.get("importance", ""),
                        "respondent": columns.get("respondent", ""),
                        "conclusion": columns.get("conclusion", ""),
                        "ecli": columns.get("ecli", ""),
                        "court_type": "echr",
                    }
                )
            logger.info(
                "HUDOC search → %s results (respondent=%s, year=%s)",
                len(cases),
                respondent_state,
                year,
            )
            return cases
        except Exception as e:
            logger.error("HUDOC search failed: %s", e)
            return []

    async def fetch_case_text(self, item_id: str, language: str = "ENG") -> str:
        """Fetch the full-text HTML of an ECHR judgment.

        Args:
            item_id: HUDOC item identifier
            language: Language code (ENG, FRE)

        Returns:
            Plain text extracted from HTML, or empty string on failure.
        """
        url = f"https://hudoc.echr.coe.int/app/conversion/docx/html/body/{item_id}"
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url, params={"language": language})
                resp.raise_for_status()
                html = resp.text

            from lxml import html as lxml_html

            doc = lxml_html.fromstring(html)
            text = doc.text_content()
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            logger.info("Fetched %s chars for HUDOC %s (%s)", len(text), item_id, language)
            return text
        except Exception as e:
            logger.error("Failed to fetch text for HUDOC %s (%s): %s", item_id, language, e)
            return ""

    async def find_finland_cases(self) -> list[dict]:
        """Find all ECHR cases involving Finland as respondent."""
        return await self.search_cases(respondent_state="FIN", limit=500)
