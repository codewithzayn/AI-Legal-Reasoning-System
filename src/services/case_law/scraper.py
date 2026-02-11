"""
Case Law Scraper for Finnish Supreme Court (KKO) and Supreme Administrative Court (KHO)
Uses Playwright to render JavaScript and extract full case content
"""

import asyncio
import re
from dataclasses import asdict, dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from src.config.logging_config import setup_logger

logger = setup_logger(__name__)


@dataclass
class Reference:
    """Represents a reference to another legal document"""

    ref_id: str  # e.g., 'KKO:2020:15' or 'RL 46:1'
    ref_type: str  # 'precedent', 'legislation'


@dataclass
class CaseLawDocument:
    """Represents a scraped case law document"""

    # Required Fields (No Defaults)
    case_id: str  # e.g., "KKO:2026:1" or "KHO 22.1.2026/149"
    court_type: str  # "supreme_court", "supreme_administrative_court"
    court_code: str  # "KKO", "KHO"
    decision_type: str  # "precedent", "other_decision"
    case_year: int

    # Optional Fields (With Defaults)
    decision_date: str | None = None  # ISO format YYYY-MM-DD
    diary_number: str | None = None
    ecli: str | None = None
    title: str = ""
    full_text: str = ""
    url: str = ""

    # Phase 3 Metadata
    primary_language: str = "Finnish"
    available_languages: list[str] = field(default_factory=lambda: ["Finnish"])

    # Parties
    applicant: str = ""
    defendant: str = ""
    respondent: str = ""

    # Lower Court
    lower_court_name: str = ""
    lower_court_date: str | None = None
    lower_court_number: str = ""
    lower_court_decision: str = ""

    # Appeal Court
    appeal_court_name: str = ""
    appeal_court_date: str | None = None
    appeal_court_number: str = ""

    # Metadata
    volume: str | None = None
    cited_regulations: list[str] = field(default_factory=list)  # e.g. "Council Regulation (EU) No 833/2014"

    # Decisions & Content
    background_summary: str = ""
    complaint: str = ""
    answer: str = ""
    decision_outcome: str = ""
    judgment: str = ""
    dissenting_opinion: bool = False
    dissenting_text: str = ""

    # Citations (Categorized)
    legal_domains: list[str] = field(default_factory=list)
    cited_laws: list[str] = field(default_factory=list)
    cited_cases: list[str] = field(default_factory=list)
    cited_government_proposals: list[str] = field(default_factory=list)
    cited_eu_cases: list[str] = field(default_factory=list)

    # Legacy & Utils
    references: list[Reference] = field(default_factory=list)
    collective_agreements: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    # Metadata
    is_precedent: bool = False

    # Content sections
    abstract: str = ""
    judges: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class CaseLawScraper:
    """Scraper for Finnish Case Law (KKO, KHO, etc.) using Index Pages"""

    # Index page URLs for listing cases by year
    INDEX_URL_PATTERNS = {
        "supreme_court": {
            "precedent": ["https://www.finlex.fi/fi/oikeuskaytanto/korkein-oikeus/ennakkopaatokset/{year}"],
            "ruling": ["https://www.finlex.fi/fi/oikeuskaytanto/korkein-oikeus/muut/{year}"],
            "leave_to_appeal": ["https://www.finlex.fi/fi/oikeuskaytanto/korkein-oikeus/valitusluvat/{year}"],
        },
        "supreme_administrative_court": {
            "precedent": ["https://www.finlex.fi/fi/oikeuskaytanto/korkein-hallinto-oikeus/ennakkopaatokset/{year}"],
            "other": ["https://www.finlex.fi/fi/oikeuskaytanto/korkein-hallinto-oikeus/muut/{year}"],
            "brief": ["https://www.finlex.fi/fi/oikeuskaytanto/korkein-hallinto-oikeus/lyhyet/{year}"],
        },
    }

    # Section markers
    SECTION_MARKERS = {
        "lower_court": "Asian käsittely alemmissa oikeuksissa",
        "court_of_appeal": "Hovioikeuden tuomio",
        "appeal_to_supreme_court": "Muutoksenhaku Korkeimmassa oikeudessa",
        "supreme_court_decision": "Korkeimman oikeuden ratkaisu",
        "reasoning": "Perustelut",
        "judgment": "Tuomiolauselma",
    }

    FOOTER_MARKERS = ["Sivun alkuun", "Lainsäädäntö", "Oikeuskäytäntö"]

    def __init__(self):
        self.browser = None
        self.page = None

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.page = await self.browser.new_page()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def fetch_year_index(self, court: str, year: int, subtype: str = None) -> list[str]:
        """Fetch all case URLs for a given court and year from the index page using Playwright"""

        if court not in self.INDEX_URL_PATTERNS:
            raise ValueError(f"No index URL pattern for court: {court}")

        patterns = self.INDEX_URL_PATTERNS[court]

        # Determine which patterns to use based on subtype
        target_index_url_patterns = []
        if subtype:
            if subtype in patterns:
                target_index_url_patterns.extend(patterns[subtype])
            else:
                logger.warning(f"Subtype {subtype} not found for {court}, skipping.")
                return []
        else:
            for p_list in patterns.values():
                target_index_url_patterns.extend(p_list)

        all_case_urls = []
        seen_urls = set()

        for index_url_pattern in target_index_url_patterns:
            index_url = index_url_pattern.format(year=year)
            logger.info(f"Fetching index: {index_url}")

            try:
                # Use Playwright to handle React/CSR
                await self.page.goto(index_url, wait_until="networkidle", timeout=60000)
                # Wait a bit for list to populate
                await self.page.wait_for_timeout(2000)

                page_num = 1
                while True:
                    logger.info(f"Processing page {page_num} for {index_url}...")
                    content = await self.page.content()
                    soup = BeautifulSoup(content, "html.parser")

                    found_on_page = 0
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if f"/{year}/" not in href:
                            continue

                        full_url = urljoin("https://www.finlex.fi", href)
                        if full_url not in seen_urls:
                            all_case_urls.append(full_url)
                            seen_urls.add(full_url)
                            found_on_page += 1

                    logger.info(f"Found {found_on_page} new cases on page {page_num}")

                    # Check for Next button
                    # Selector based on debug analysis: a[aria-label="Seuraava sivu"]
                    # If it exists and is not disabled, click it.

                    # We need to re-locate it in the live page context (soup is stale)
                    next_btn = self.page.locator('a[aria-label="Seuraava sivu"]').first

                    if not await next_btn.is_visible():
                        logger.info("No 'Next' button found (single page result).")
                        break

                    is_disabled = await next_btn.get_attribute("aria-disabled") == "true"
                    if is_disabled:
                        logger.info("Next button is disabled. End of pagination.")
                        break

                    # Click and wait
                    logger.info("Navigating to next page...")
                    await next_btn.click()
                    # Wait for network idle or strictly wait for load
                    # Since href="#", it's a SPA transition. Safe to wait for a bit.
                    await self.page.wait_for_load_state("networkidle")
                    await self.page.wait_for_timeout(2000)
                    page_num += 1

            except Exception as e:
                logger.error(f"Error fetching index {index_url}: {e}")

        return sorted(list(all_case_urls))

    async def fetch_year(self, court: str, year: int, subtype: str = None) -> list[CaseLawDocument]:
        """
        Fetch all cases for a court and year using index pages

        Args:
            court: "supreme_court", "supreme_administrative_court"
            year: Year to fetch
            subtype: Optional subtype (e.g. "precedent", "ruling")
        """
        logger.info(f"Starting year fetch: {court} {year} (subtype={subtype})")

        urls = await self.fetch_year_index(court, year, subtype)

        if not urls:
            logger.warning(f"No cases found in index for {court} {year}")
            return []

        logger.info(f"Found {len(urls)} cases to fetch")

        documents = []
        for i, url in enumerate(urls):
            logger.info("Fetching case %s/%s: %s", i + 1, len(urls), url)
            doc = await self.fetch_case_by_url(url, court, year)
            if doc:
                documents.append(doc)
            else:
                logger.warning("Failed to fetch/parse: %s", url)
            # Short delay between requests to reduce connection resets / rate limits
            if i < len(urls) - 1:
                await asyncio.sleep(1)

        logger.info("Completed year %s: %s cases extracted", year, len(documents))
        return documents

    def _case_id_to_url(self, case_id: str, court: str, subtype: str | None) -> str | None:
        """Build Finlex case page URL from case_id (e.g. KKO:2018:72).
        Returns None if court/subtype not supported or case_id format invalid.
        """
        parts = (case_id or "").strip().replace(" ", ":").split(":")
        if len(parts) < 3:
            return None
        try:
            year = int(parts[-2])
            num = parts[-1]
        except (ValueError, IndexError):
            return None
        if court not in self.INDEX_URL_PATTERNS:
            return None
        patterns = self.INDEX_URL_PATTERNS[court]
        if not subtype or subtype not in patterns:
            return None
        base = patterns[subtype][0].format(year=year)
        return f"{base}/{num}"

    async def fetch_cases_by_ids(
        self, court: str, year: int, subtype: str | None, case_ids: list[str]
    ) -> list[CaseLawDocument]:
        """Fetch only the given case IDs (e.g. ['KKO:2018:72', 'KKO:2018:73']).
        Uses direct case page URLs; does not scrape the full year index.
        """
        if not case_ids:
            return []
        seen = set()
        documents = []
        for case_id in case_ids:
            cid = (case_id or "").strip()
            if not cid or cid in seen:
                continue
            seen.add(cid)
            url = self._case_id_to_url(cid, court, subtype)
            if not url:
                logger.warning("Cannot build URL for case_id=%s (court=%s, subtype=%s)", cid, court, subtype)
                continue
            logger.info("Fetching case %s: %s", cid, url)
            doc = await self.fetch_case_by_url(url, court, year)
            if doc:
                documents.append(doc)
            else:
                logger.warning("Failed to fetch: %s", cid)
        return documents

    @staticmethod
    def _is_retriable_error(exc: Exception) -> bool:
        """True if the error is transient (network/timeout) and worth retrying."""
        msg = (exc.args[0] if exc.args else "") or str(exc)
        msg_lower = msg.lower()
        retriable = (
            "err_internet_disconnected" in msg_lower
            or "err_connection" in msg_lower
            or "err_network" in msg_lower
            or "timeout" in msg_lower
            or "net::" in msg
        )
        return bool(retriable)

    async def fetch_case_by_url(self, url: str, court: str, year: int, max_retries: int = 3) -> CaseLawDocument | None:
        """Fetch and parse a single case by its direct URL. Retries on transient network errors."""
        for attempt in range(max_retries):
            try:
                # Use 'load' (not networkidle) so slow Finlex/analytics don't cause timeout; 2 min timeout
                response = await self.page.goto(url, wait_until="load", timeout=120000)

                if response and response.status == 404:
                    logger.warning("Case %s returned 404 status via Playwright", url)
                    return None

                await self.page.wait_for_timeout(2000)

                page_title = await self.page.title()
                if "404" in page_title or "Sivua ei löytynyt" in page_title:
                    logger.warning("Case %s returned 404 based on title", url)
                    return None

                full_text = await self.page.evaluate("""() => {
                const article = document.querySelector('article');
                if (article) return article.innerText;
                const main = document.querySelector('main');
                if (main) return main.innerText;
                return document.body.innerText;
            }""")

                if "Sivua ei löytynyt" in full_text:
                    logger.warning("Case %s content indicates 404", url)
                    return None

                url_last = url.rstrip("/").split("/")[-1]
                try:
                    url_number = int(url_last)
                    url_suffix = None
                except ValueError:
                    url_number = 0
                    url_suffix = url_last

                document = self._parse_case_text(full_text, court, year, url_number, url, url_suffix=url_suffix)
                return document

            except Exception as e:
                if self._is_retriable_error(e) and attempt < max_retries - 1:
                    delay = (attempt + 1) * 5  # 5s, 10s, 15s
                    logger.warning(
                        "Attempt %s/%s failed for %s (%s), retrying in %ss...",
                        attempt + 1,
                        max_retries,
                        url,
                        e,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error("Error fetching case %s: %s", url, e)
                    return None
        logger.error("Failed to fetch/parse: %s", url)
        return None

    # ----------------------------------------------------------------
    #  Metadata header labels (Finnish website text -> field mapping)
    # ----------------------------------------------------------------
    # The Finlex website renders a structured header block at the top of each document.
    # Lines alternate: label line, then value line(s), until the abstract paragraph.
    _HEADER_LABELS_FI = {
        "Asiasanat": "keywords",
        "Keywords": "keywords",
        "Tapausvuosi": "case_year",
        "Case year": "case_year",
        "Antopäivä": "decision_date",
        "Date of issue": "decision_date",
        "Diaarinumero": "diary_number",
        "Diary number": "diary_number",
        "Taltio": "volume",
        "Volume": "volume",
        "ECLI-tunnus": "ecli",
        "ECLI code": "ecli",
    }
    # Lines to skip entirely (navigation noise from the website)
    _SKIP_LINES = {
        "Kieliversiot",
        "Language versions",
        "Suomi",
        "Ruotsi",
        "Finnish",
        "Swedish",
        "Kopioi ECLI-linkki",
        "Copy ECLI link",
    }

    # Judge attribution patterns (last paragraph)
    _JUDGE_PATTERN = re.compile(
        r"^(Asian (?:ovat|on) ratkaiss\w+|The (?:case|matter) has been (?:resolved|decided))\s+",
        re.IGNORECASE,
    )

    def _extract_header_metadata(self, text: str) -> dict:
        """
        Parse the structured metadata header from the top of full_text.
        Returns dict with: keywords, decision_date, diary_number, volume, ecli,
        header_end_index (char position where the body starts).
        """
        lines = text.split("\n")
        result: dict = {"keywords": [], "header_end_index": 0}
        current_field = None

        for i, raw_line in enumerate(lines):
            line = raw_line.strip()

            # Empty lines: check if header is ending (next non-empty line is long = abstract)
            if not line:
                if current_field and i > 5 and self._is_body_start_ahead(lines, i):
                    result["header_end_index"] = sum(len(lines[k]) + 1 for k in range(i + 1))
                    break
                continue

            if line in self._SKIP_LINES:
                continue

            if line in self._HEADER_LABELS_FI:
                current_field = self._HEADER_LABELS_FI[line]
                continue

            if current_field:
                current_field = self._store_header_value(result, current_field, line)
                continue

            # Long text with no active field = header is done
            if len(line) > 80:
                result["header_end_index"] = sum(len(lines[k]) + 1 for k in range(i))
                break

        return result

    @staticmethod
    def _is_body_start_ahead(lines: list[str], blank_idx: int) -> bool:
        """Check if the next non-empty line after blank_idx is a long paragraph (= abstract)."""
        for j in range(blank_idx + 1, min(blank_idx + 5, len(lines))):
            next_line = lines[j].strip()
            if next_line and len(next_line) > 80:
                return True
            if next_line:
                return False
        return False

    @staticmethod
    def _store_header_value(result: dict, field: str, value: str) -> str | None:
        """Store a header value into result dict. Returns the next active field (None to reset)."""
        if field == "keywords":
            result["keywords"].append(value)
            return field  # keywords can be multi-line
        if field != "case_year":
            result[field] = value
        return None  # single-value fields: reset after reading

    def _extract_judges_line(self, text: str) -> str:
        """Extract the judge attribution from the last few lines of full_text."""
        lines = text.strip().split("\n")
        for raw_line in reversed(lines[-10:]):
            stripped = raw_line.strip()
            if self._JUDGE_PATTERN.match(stripped):
                return stripped
        return ""

    def _convert_finnish_date(self, date_str: str) -> str:
        """Convert Finnish date '7.1.2026' to ISO '2026-01-07'."""
        m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", date_str.strip())
        if m:
            return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        return date_str  # Return as-is if not parseable

    def _parse_case_text(
        self, text: str, court: str, year: int, number: int, url: str, *, url_suffix: str | None = None
    ) -> CaseLawDocument:
        """
        Create a CaseLawDocument from the scraped text.
        Extracts metadata from the structured header block and populates all available fields.
        url_suffix: when URL path ends with a non-numeric segment (e.g. "II-219" for 1926 precedents), use for case_id.
        """
        court_prefix = "KKO" if court == "supreme_court" else "KHO"

        # Extract case_id: prefer old format (KKO:1926-I-10, KKO:1926-II-219) from first line, then modern format
        first_line = (text.split("\n")[0] or "").strip()
        old_format_match = re.match(rf"^({court_prefix}:\d{{4}}-[IVXLCDM]+-\d+)\b", first_line, re.IGNORECASE)
        if old_format_match:
            final_id = old_format_match.group(1)
        else:
            case_id_match = re.search(rf"{court_prefix}[:\s]*\d{{4}}[:\s]*\d+", text)
            if not case_id_match:
                case_id_match = re.search(rf"{court_prefix}\s+\d{{1,2}}\.\d{{1,2}}\.{year}/\d+", text)
            if case_id_match:
                raw_id = case_id_match.group(0)
                final_id = raw_id if "/" in raw_id else raw_id.replace(" ", ":")
            elif url_suffix:
                final_id = f"{court_prefix}:{year}:{url_suffix}"
            else:
                final_id = f"{court_prefix}:{year}:{number}"

        # Decision type from URL
        decision_type = "precedent"
        if "muut-paatokset" in url or "muut/" in url:
            decision_type = "other_decision"
        elif "lyhyet-ratkaisuselosteet" in url or "lyhyet/" in url:
            decision_type = "brief_explanation"

        # Extract metadata from the structured header in full_text
        meta = self._extract_header_metadata(text)
        judges_line = self._extract_judges_line(text)

        # Convert Finnish date to ISO
        raw_date = meta.get("decision_date", "")
        decision_date = self._convert_finnish_date(raw_date) if raw_date else None

        doc = CaseLawDocument(
            case_id=final_id,
            court_type=court,
            court_code=court_prefix,
            decision_type=decision_type,
            case_year=year,
            url=url,
            full_text=text,
            is_precedent=(decision_type == "precedent"),
            primary_language="Finnish",
            # Populated metadata from header
            decision_date=decision_date,
            diary_number=meta.get("diary_number"),
            ecli=meta.get("ecli"),
            volume=meta.get("volume"),
            legal_domains=meta.get("keywords", []),
            judges=judges_line,
        )

        return doc


# Standalone function for simple usage
async def scrape_supreme_court_year(year: int) -> list[CaseLawDocument]:
    """Convenience function to scrape a full year of Supreme Court cases"""
    async with CaseLawScraper() as scraper:
        return await scraper.fetch_year("supreme_court", year)


async def scrape_supreme_administrative_court_year(year: int) -> list[CaseLawDocument]:
    """Convenience function to scrape a full year of Supreme Administrative Court cases"""
    async with CaseLawScraper() as scraper:
        return await scraper.fetch_year("supreme_administrative_court", year)
