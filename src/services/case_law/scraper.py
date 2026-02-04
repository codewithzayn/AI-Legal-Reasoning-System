"""
Case Law Scraper for Finnish Supreme Court (KKO) and Supreme Administrative Court (KHO)
Uses Playwright to render JavaScript and extract full case content
"""

import asyncio
import re
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from src.config.logging_config import setup_logger

logger = setup_logger(__name__)


@dataclass
class Reference:
    """Represents a reference to another legal document"""
    ref_id: str      # e.g., 'KKO:2020:15' or 'RL 46:1'
    ref_type: str    # 'precedent', 'legislation'


@dataclass
class CaseLawDocument:
    """Represents a scraped case law document"""
    # Required Fields (No Defaults)
    case_id: str                    # e.g., "KKO:2026:1" or "KHO 22.1.2026/149"
    court_type: str                 # "supreme_court", "supreme_administrative_court"
    court_code: str                 # "KKO", "KHO"
    decision_type: str              # "precedent", "other_decision"
    case_year: int
    
    # Optional Fields (With Defaults)
    decision_date: Optional[str] = None # ISO format YYYY-MM-DD
    diary_number: Optional[str] = None
    ecli: Optional[str] = None
    title: str = ""
    full_text: str = ""
    url: str = ""
    
    # Phase 3 Metadata
    primary_language: str = "Finnish"
    available_languages: List[str] = field(default_factory=lambda: ["Finnish"])
    
    # Parties
    applicant: str = ""
    defendant: str = ""
    respondent: str = ""
    
    # Lower Court
    lower_court_name: str = ""
    lower_court_date: Optional[str] = None
    lower_court_number: str = ""
    lower_court_decision: str = ""
    
    # Appeal Court
    appeal_court_name: str = ""
    appeal_court_date: Optional[str] = None
    appeal_court_number: str = ""
    
    # Metadata
    volume: Optional[str] = None
    cited_regulations: List[str] = field(default_factory=list) # e.g. "Council Regulation (EU) No 833/2014"
    
    # Decisions & Content
    background_summary: str = ""
    complaint: str = ""
    answer: str = ""
    decision_outcome: str = ""
    judgment: str = ""
    dissenting_opinion: bool = False
    dissenting_text: str = ""
    
    # Citations (Categorized)
    legal_domains: List[str] = field(default_factory=list)
    cited_laws: List[str] = field(default_factory=list)
    cited_cases: List[str] = field(default_factory=list)
    cited_government_proposals: List[str] = field(default_factory=list)
    cited_eu_cases: List[str] = field(default_factory=list)

    # Legacy & Utils
    references: List[Reference] = field(default_factory=list)
    collective_agreements: List[dict] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    
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
            "leave_to_appeal": ["https://www.finlex.fi/fi/oikeuskaytanto/korkein-oikeus/valitusluvat/{year}"]
        },
        "supreme_administrative_court": {
            "precedent": ["https://www.finlex.fi/fi/oikeuskaytanto/korkein-hallinto-oikeus/ennakkopaatokset/{year}"],
            "other": ["https://www.finlex.fi/fi/oikeuskaytanto/korkein-hallinto-oikeus/muut/{year}"],
            "brief": ["https://www.finlex.fi/fi/oikeuskaytanto/korkein-hallinto-oikeus/lyhyet/{year}"]
        }
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
            
    async def fetch_year_index(self, court: str, year: int, subtype: str = None) -> List[str]:
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
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    found_on_page = 0
                    for a in soup.find_all('a', href=True):
                        href = a['href']
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

    async def fetch_year(self, court: str, year: int, subtype: str = None) -> List[CaseLawDocument]:
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
            logger.info(f"Fetching case {i+1}/{len(urls)}: {url}")
            doc = await self.fetch_case_by_url(url, court, year)
            if doc:
                documents.append(doc)
            else:
                logger.warning(f"Failed to fetch/parse: {url}")
                
        logger.info(f"Completed year {year}: {len(documents)} cases extracted")
        return documents

    async def fetch_case_by_url(self, url: str, court: str, year: int) -> Optional[CaseLawDocument]:
        """Fetch and parse a single case by its direct URL"""
        try:
            response = await self.page.goto(url, wait_until="networkidle", timeout=60000)
            
            if response and response.status == 404:
                logger.warning(f"Case {url} returned 404 status via Playwright")
                return None
                
            await self.page.wait_for_timeout(1000)
            
            # Validate via title or visible content instead of raw HTML source
            page_title = await self.page.title()
            if "404" in page_title or "Sivua ei löytynyt" in page_title:
                 logger.warning(f"Case {url} returned 404 based on title")
                 return None
                 
            full_text = await self.page.evaluate('''() => {
            const article = document.querySelector('article');
            if (article) return article.innerText;
            const main = document.querySelector('main');
            if (main) return main.innerText;
            return document.body.innerText;
        }''')
            
            if "Sivua ei löytynyt" in full_text:
                 logger.warning(f"Case {url} content indicates 404")
                 return None
            
            # Extract case number from URL for fallback
            # e.g. .../2025/23 -> 23
            try:
                url_number = int(url.split("/")[-1])
            except ValueError:
                url_number = 0
            
            document = self._parse_case_text(full_text, court, year, url_number, url)
            return document
            
        except Exception as e:
            logger.error(f"Error fetching case {url}: {e}")
            return None

    
    def _parse_case_text(self, text: str, court: str, year: int, number: int, url: str) -> CaseLawDocument:
        """
        Create a raw CaseLawDocument from the text.
        Detailed parsing is handled by the regex extractor at ingestion.
        This method only populates identifiers and full_text.
        """
        
        court_prefix = "KKO" if court == "supreme_court" else "KHO"
        
        # simple ID extraction for identification
        case_id_match = re.search(rf"{court_prefix}[:\s]*\d{{4}}[:\s]*\d+", text)
        if not case_id_match:
            case_id_match = re.search(rf"{court_prefix}\s+\d{{1,2}}\.\d{{1,2}}\.{year}/\d+", text)
        
        if case_id_match:
            raw_id = case_id_match.group(0)
            final_id = raw_id if "/" in raw_id else raw_id.replace(" ", ":")
        else:
            final_id = f"{court_prefix}:{year}:{number}"
            
        # Determine decision type based on URL (basic classification)
        decision_type = "precedent"
        if "muut-paatokset" in url or "muut/" in url:
            decision_type = "other_decision"
        elif "lyhyet-ratkaisuselosteet" in url or "lyhyet/" in url:
            decision_type = "brief_explanation"

        doc = CaseLawDocument(
            case_id=final_id,
            court_type=court,
            court_code=court_prefix,
            decision_type=decision_type,
            case_year=year,
            url=url,
            full_text=text,
            is_precedent=(decision_type == "precedent"),
            # All other fields defaulting to empty, to be populated by AI
            primary_language="Finnish"
        )
        
        return doc



# Standalone function for simple usage
async def scrape_supreme_court_year(year: int) -> List[CaseLawDocument]:
    """Convenience function to scrape a full year of Supreme Court cases"""
    async with CaseLawScraper() as scraper:
        return await scraper.fetch_year("supreme_court", year)


async def scrape_supreme_administrative_court_year(year: int) -> List[CaseLawDocument]:
    """Convenience function to scrape a full year of Supreme Administrative Court cases"""
    async with CaseLawScraper() as scraper:
        return await scraper.fetch_year("supreme_administrative_court", year)
