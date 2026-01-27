"""
Case Law Scraper for Finnish Supreme Court (KKO) and Supreme Administrative Court (KHO)
Uses Playwright to render JavaScript and extract full case content
"""

import asyncio
import re
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from playwright.async_api import async_playwright
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
    case_id: str                    # e.g., "KKO:2026:1"
    court: str                      # "kko" or "kho"
    year: int
    case_number: int
    ecli: Optional[str] = None      # ECLI:FI:KKO:2026:1
    date: Optional[str] = None      # 7.1.2026
    diary_number: Optional[str] = None  # R2024/357
    keywords: List[str] = field(default_factory=list)
    references: List[Reference] = field(default_factory=list)  # Extracted references
    metadata: Dict = field(default_factory=dict) # JSONB metadata
    document_uri: str = "" # Unique URI (e.g. finlex/kko/2026/1)
    url: str = "" 
    
    # Content sections
    abstract: str = ""
    lower_court: str = ""
    court_of_appeal: str = ""
    appeal_to_supreme_court: str = ""
    supreme_court_decision: str = ""
    reasoning: str = ""
    judgment: str = ""
    judges: str = ""
    full_text: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)


class CaseLawScraper:
    """Scraper for KKO and KHO case law from Finlex using Playwright"""
    
    # URL patterns for different courts (Finnish version - has static-ish content)
    URL_PATTERNS = {
        "supreme_court": "https://www.finlex.fi/fi/oikeuskaytanto/korkein-oikeus/ennakkopaatokset/{year}/{number}",
        "supreme_administrative_court": "https://www.finlex.fi/fi/oikeuskaytanto/korkein-hallinto-oikeus/ennakkopaatokset/{year}/{number}"
    }
    
    # Finnish section markers for parsing (ordered)
    SECTION_MARKERS = {
        "lower_court": "Asian käsittely alemmissa oikeuksissa",
        "court_of_appeal": "Hovioikeuden tuomio",  # More specific
        "appeal_to_supreme_court": "Muutoksenhaku Korkeimmassa oikeudessa",
        "supreme_court_decision": "Korkeimman oikeuden ratkaisu",
        "reasoning": "Perustelut",
        "judgment": "Tuomiolauselma",
    }
    
    # Footer markers that indicate end of case content
    FOOTER_MARKERS = [
        "Sivun alkuun",  # "Top of page" link
        "Lainsäädäntö",  # Navigation footer
        "Oikeuskäytäntö",  # Navigation footer
    ]
    
    def __init__(self):
        self.browser = None
        self.page = None
    
    async def __aenter__(self):
        """Async context manager entry - launch browser"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.page = await self.browser.new_page()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - close browser"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def fetch_case(self, court: str, year: int, number: int) -> Optional[CaseLawDocument]:
        """
        Fetch a single case by court, year, and number
        
        Args:
            court: "supreme_court" or "supreme_administrative_court"
            year: Year (e.g., 2026)
            number: Case number (e.g., 1)
            
        Returns:
            CaseLawDocument if found, None if 404
        """
        if court not in self.URL_PATTERNS:
            raise ValueError(f"Invalid court: {court}. Must be 'supreme_court' or 'supreme_administrative_court'")
        
        initial_url = self.URL_PATTERNS[court].format(year=year, number=number)
        
        try:
            response = await self.page.goto(initial_url, wait_until="networkidle")
            
            # Get actual final URL (handling redirects)
            final_url = self.page.url
            
            # Check for 404
            if response and response.status == 404:
                logger.info(f"Case not found (404): {court.upper()}:{year}:{number}")
                return None
            
            # Wait for content to load
            await self.page.wait_for_timeout(2000)
            
            # Check for "not found" text in page content
            page_content = await self.page.content()
            if "The document you were looking for was not found" in page_content or \
               "Hakemaasi asiakirjaa ei löytynyt" in page_content:
                logger.info(f"Case not found (page text): {court.upper()}:{year}:{number}")
                return None
            
            # Get full text content
            full_text = await self.page.evaluate('''() => {
                const main = document.querySelector('main') || document.querySelector('article') || document.body;
                return main.innerText;
            }''')
            
            # Parse the content
            document = self._parse_case_text(full_text, court, year, number, final_url)
            
            logger.info(f"Successfully extracted: {document.case_id} ({len(document.full_text)} chars)")
            return document
            
        except Exception as e:
            logger.error(f"Error fetching case {court.upper()}:{year}:{number}: {e}")
            return None
    
    async def fetch_year(self, court: str, year: int, max_cases: int = 200) -> List[CaseLawDocument]:
        """
        Fetch all cases for a given court and year
        
        Args:
            court: "kko" or "kho"
            year: Year to fetch
            max_cases: Maximum cases to try (safety limit)
            
        Returns:
            List of CaseLawDocument objects
        """
        logger.info(f"Starting year fetch: {court.upper()} {year}")
        
        documents = []
        consecutive_not_found = 0
        
        for number in range(1, max_cases + 1):
            doc = await self.fetch_case(court, year, number)
            
            if doc is None:
                consecutive_not_found += 1
                # Stop after 3 consecutive 404s (gap safety)
                if consecutive_not_found >= 3:
                    logger.info(f"Stopping at case {number} after {consecutive_not_found} consecutive 404s")
                    break
            else:
                consecutive_not_found = 0
                documents.append(doc)
        
        logger.info(f"Completed year {year}: {len(documents)} cases extracted")
        return documents
    
    def _parse_case_text(self, text: str, court: str, year: int, number: int, url: str) -> CaseLawDocument:
        """Parse the full case text into structured sections"""
        
        court_prefix = "KKO" if court == "kko" else "KHO"
        
        # Extract metadata
        case_id_match = re.search(rf"{court_prefix}[:\s]*\d{{4}}[:\s]*\d+", text)
        ecli_match = re.search(rf"ECLI:FI:{court_prefix}:\d{{4}}:\d+", text)
        date_match = re.search(r"Antopäivä\s*\n?(\d{1,2}\.\d{1,2}\.\d{4})", text)
        diary_match = re.search(r"Diaarinumero\s*\n?([A-Z]+\d+/\d+)", text)
        
        # Extract keywords
        keywords = []
        keywords_match = re.search(r"Asiasanat\s*\n(.*?)Tapausvuosi", text, re.DOTALL)
        if keywords_match:
            keywords_text = keywords_match.group(1).strip()
            keywords = [k.strip() for k in keywords_text.split('\n') if k.strip()]
        
        # Create document
        doc = CaseLawDocument(
            case_id=case_id_match.group(0).replace(" ", ":") if case_id_match else f"{court_prefix}:{year}:{number}",
            court=court,
            year=year,
            case_number=number,
            ecli=ecli_match.group(0) if ecli_match else None,
            date=date_match.group(1) if date_match else None,
            diary_number=diary_match.group(1) if diary_match else None,
            keywords=keywords,
            url=url,
            document_uri=f"finlex/{court}/{year}/{number}",
            metadata={
                "ecli": ecli_match.group(0) if ecli_match else None,
                "date": date_match.group(1) if date_match else None,
                "diary_number": diary_match.group(1) if diary_match else None,
                "keywords": keywords
            },
            full_text=text
        )
        
        # Extract sections
        all_markers = list(self.SECTION_MARKERS.values())
        
        for section_key, marker in self.SECTION_MARKERS.items():
            section_text = self._extract_section(text, marker, all_markers)
            setattr(doc, section_key, section_text)
        
        # Extract abstract (summary before first section)
        doc.abstract = self._extract_abstract(text, all_markers)
        
        # Extract references (precedents and legislation)
        doc.references = self._extract_references(text, court)
        
        # Extract judges from judgment section
        if doc.judgment:
            judges_match = re.search(r"Asian ovat ratkaisseet.*$", doc.judgment, re.DOTALL)
            if judges_match:
                doc.judges = judges_match.group(0)
        
        return doc
    
    def _extract_references(self, text: str, current_court: str) -> List[Reference]:
        """Extract references to other cases and legislation"""
        references = []
        seen = set()
        
        # 1. Precedents (KKO:YYYY:NN or KHO:YYYY:NN)
        precedent_pattern = r"(KKO|KHO):(\d{4}):(\d+)"
        for match in re.finditer(precedent_pattern, text):
            court, year, number = match.groups()
            ref_id = f"{court}:{year}:{number}"
            
            # Skip self-reference if possible (simple check)
            
            if ref_id not in seen:
                references.append(Reference(ref_id=ref_id, ref_type="precedent"))
                seen.add(ref_id)
        
        # 2. Legislation (e.g., RL 21:1, OK 30:3)
        # Common Finnish legal abbreviations: RL (Rikoslaki), OK (Oikeudenkäymiskaari), etc.
        legislation_patterns = [
            r"(RL|OK|PK|VahL|HolhousL)\s+(\d+)\s+(?:luku|luvun)\s+(\d+)\s+§",  # RL 21 luku 1 §
            r"(RL|OK|PK|VahL|HolhousL)\s+(\d+)\s+(?:luku|luvun)\s+(\d+)\s+ja\s+(\d+)\s+§",  # RL 21 luku 1 ja 2 §
        ]
        
        for pattern in legislation_patterns:
            for match in re.finditer(pattern, text):
                groups = match.groups()
                code = groups[0]
                chapter = groups[1]
                section = groups[2]
                
                ref_id = f"{code} {chapter}:{section}"
                
                if ref_id not in seen:
                    references.append(Reference(ref_id=ref_id, ref_type="legislation"))
                    seen.add(ref_id)
        
        return references
    
    def _extract_section(self, text: str, start_marker: str, all_markers: list) -> str:
        """Extract text between start_marker and the next section marker or footer"""
        
        start_pos = text.find(start_marker)
        if start_pos == -1:
            return ""
        
        # Move past the marker
        start_pos += len(start_marker)
        
        # Find the next section marker
        end_pos = len(text)
        
        # Check other section markers
        for marker in all_markers:
            if marker == start_marker:
                continue
            pos = text.find(marker, start_pos)
            if pos > start_pos and pos < end_pos:
                end_pos = pos
        
        # Also check footer markers (for last section)
        for footer in self.FOOTER_MARKERS:
            pos = text.find(footer, start_pos)
            if pos > start_pos and pos < end_pos:
                end_pos = pos
        
        return text[start_pos:end_pos].strip()
    
    def _extract_abstract(self, text: str, all_markers: list) -> str:
        """Extract abstract/summary from before the first section"""
        
        # Find position after ECLI metadata block
        ecli_pos = text.find("ECLI-tunnus")
        if ecli_pos == -1:
            ecli_pos = text.find("ECLI:FI:")
        
        if ecli_pos == -1:
            return ""
        
        # Find start of abstract (after ECLI link)
        abstract_start = text.find("\n", ecli_pos + 30)
        if abstract_start == -1:
            return ""
        
        # Find the first section marker
        first_section_pos = len(text)
        for marker in all_markers:
            pos = text.find(marker)
            if pos > abstract_start and pos < first_section_pos:
                first_section_pos = pos
        
        abstract = text[abstract_start:first_section_pos].strip()
        # Clean up
        abstract = re.sub(r"Kopioi ECLI-linkki\s*", "", abstract)
        return abstract.strip()


# Standalone function for simple usage
async def scrape_supreme_court_year(year: int) -> List[CaseLawDocument]:
    """Convenience function to scrape a full year of Supreme Court cases"""
    async with CaseLawScraper() as scraper:
        return await scraper.fetch_year("supreme_court", year)


async def scrape_supreme_administrative_court_year(year: int) -> List[CaseLawDocument]:
    """Convenience function to scrape a full year of Supreme Administrative Court cases"""
    async with CaseLawScraper() as scraper:
        return await scraper.fetch_year("supreme_administrative_court", year)
