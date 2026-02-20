"""
CURIA Scraper — fetches recent CJEU/General Court decisions not yet in EUR-Lex.

Uses httpx + BeautifulSoup (same pattern as the existing Finlex scraper)
to fetch the latest decisions from CURIA's public search interface.
"""

import re
from datetime import datetime, timedelta

import httpx
from bs4 import BeautifulSoup

from src.config.logging_config import setup_logger
from src.config.settings import config

logger = setup_logger(__name__)


class CuriaScraper:
    """Scraper for recent CJEU/General Court decisions from CURIA."""

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or config.CURIA_BASE_URL

    async def fetch_recent_decisions(self, days: int = 14, language: str = "en") -> list[dict]:
        """Fetch recent decisions from CURIA (last N days).

        Args:
            days: Number of days to look back.
            language: Language code ('en', 'fi').

        Returns:
            List of dicts with: case_number, title, date, ecli, url, court_type, full_text
        """
        date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        date_to = datetime.now().strftime("%Y-%m-%d")

        # CURIA search URL for recent judgments
        search_url = (
            f"{self.base_url}/juris/documents.jsf"
            f"?critereEcli=ECLI:EU:*"
            f"&typeRecherche=CELLAR"
            f"&dates={date_from}"
            f"&datee={date_to}"
            f"&language={language}"
        )

        decisions = []
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(search_url)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

            # Parse search result rows
            rows = soup.select("table.detail_table_documents tr") or soup.select(".result_table tr")
            for row in rows:
                decision = self._parse_result_row(row, language)
                if decision:
                    decisions.append(decision)

            logger.info("CURIA scraper → %s decisions (last %s days)", len(decisions), days)
        except Exception as e:
            logger.error("CURIA scraper failed: %s", e)

        return decisions

    async def fetch_decision_by_case_number(self, case_number: str, language: str = "en") -> dict | None:
        """Fetch a specific decision by case number (e.g. C-311/18).

        Args:
            case_number: EU case number.
            language: Language code.

        Returns:
            Dict with case metadata and full_text, or None.
        """
        url = f"{self.base_url}/juris/liste.jsf?num={case_number}&language={language}"
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

            # Extract case details from the results page
            title_el = soup.select_one(".outputTitle, .titre_complet, h1")
            title = title_el.get_text(strip=True) if title_el else case_number

            # Try to find the full text link and follow it
            text_link = soup.select_one('a[href*="TXT"]') or soup.select_one('a[href*="document"]')
            full_text = ""
            if text_link and text_link.get("href"):
                text_url = text_link["href"]
                if not text_url.startswith("http"):
                    text_url = f"{self.base_url}{text_url}"
                text_resp = await client.get(text_url)
                if text_resp.status_code == 200:
                    text_soup = BeautifulSoup(text_resp.text, "html.parser")
                    content_div = (
                        text_soup.select_one("#document_content")
                        or text_soup.select_one(".documentContent")
                        or text_soup.body
                    )
                    if content_div:
                        full_text = content_div.get_text(separator="\n", strip=True)

            # Extract ECLI
            ecli_match = re.search(r"ECLI:EU:[CT]:\d{4}:\d+", soup.get_text())
            ecli = ecli_match.group(0) if ecli_match else ""

            # Determine court type
            court_type = "cjeu"
            if case_number.startswith("T-"):
                court_type = "general_court"

            return {
                "case_number": case_number,
                "title": title,
                "ecli": ecli,
                "url": url,
                "court_type": court_type,
                "full_text": full_text,
            }
        except Exception as e:
            logger.error("CURIA fetch for %s failed: %s", case_number, e)
            return None

    def _parse_result_row(self, row, language: str) -> dict | None:
        """Parse a single search result row from CURIA HTML."""
        cells = row.select("td")
        if not cells or len(cells) < 2:
            return None

        # Try to extract case number, title, date from cells
        text_content = [c.get_text(strip=True) for c in cells]
        case_number = ""
        title = ""
        date_str = ""
        ecli = ""

        for text in text_content:
            if re.match(r"^[CT]-\d+/\d{2}", text):
                case_number = text
            elif re.match(r"\d{2}/\d{2}/\d{4}", text):
                date_str = text
            elif text.startswith("ECLI:"):
                ecli = text
            elif len(text) > 20 and not title:
                title = text

        if not case_number:
            return None

        court_type = "cjeu"
        if case_number.startswith("T-"):
            court_type = "general_court"

        url = f"{self.base_url}/juris/liste.jsf?num={case_number}&language={language}"

        return {
            "case_number": case_number,
            "title": title or case_number,
            "date": date_str,
            "ecli": ecli,
            "url": url,
            "court_type": court_type,
            "full_text": "",  # needs separate fetch
        }
