"""
Finlex Open Data API Client (Async)
"""

import re

import httpx

from src.config.logging_config import setup_logger

logger = setup_logger(__name__)


class FinlexAPI:
    """Async client for Finlex Open Data API"""

    BASE_URL = "https://opendata.finlex.fi/finlex/avoindata/v1"

    def __init__(self) -> None:
        self.headers = {"User-Agent": "AI-Legal-Reasoning-System/1.0"}

    async def get_document(self, uri: str) -> str:
        """Deprecated: Use fetch_document_xml instead"""
        return await self.fetch_document_xml(uri)

    def _extract_document_type(self, uri: str) -> str:
        """Extract document type from Finlex URI"""
        parts = uri.split("/")
        try:
            category_idx = parts.index("fi") + 1
            type_idx = category_idx + 1
            return parts[type_idx]
        except (ValueError, IndexError):
            return "unknown"

    def _extract_year(self, uri: str) -> int:
        """Extract year from Finlex URI"""
        parts = uri.split("/")
        try:
            category_idx = parts.index("fi") + 1
            year_idx = category_idx + 2
            return int(parts[year_idx])
        except (ValueError, IndexError):
            return 0

    def _extract_document_category(self, uri: str) -> str:
        """Extract document category from Finlex URI (act, judgment, or doc)"""
        parts = uri.split("/")
        try:
            category_idx = parts.index("fi") + 1
            return parts[category_idx]  # act, judgment, or doc
        except (ValueError, IndexError):
            return "unknown"

    async def fetch_document_list(
        self, category: str, doc_type: str, year: int, page: int = 1, limit: int = 10
    ) -> list:
        """
        Fetch list of documents for bulk ingestion

        Args:
            category: Document category (act, judgment, doc)
            year: Year to fetch
            page: Page number
            limit: Results per page

        Returns:
            List of documents with akn_uri and status
        """
        url = f"{self.BASE_URL}/akn/fi/{category}/{doc_type}/list"

        params = {"startYear": year, "page": page, "limit": limit}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self.headers, params=params, timeout=30)
                response.raise_for_status()
                return response.json()
        except httpx.RequestError as e:
            logger.error(f"API error: {e}")
            return []

    def _extract_language(self, uri: str) -> str:
        """
        Extract language code from Finlex URI dynamically

        Args:
            uri: Finlex document URI (e.g. .../fin@ or .../swe@ or .../eng@)

        Returns:
            Language code extracted from URI, defaults to 'fin'
        """
        # Match pattern: /xxx@ where xxx is the language code
        match = re.search(r"/([a-z]{2,3})@", uri)
        if match:
            return match.group(1)
        return "fin"  # Default to Finnish

    async def fetch_document_xml(self, akn_uri: str) -> str:
        """
        Fetch XML content for a document

        Args:
            akn_uri: Full Akoma Ntoso URI

        Returns:
            XML content as string
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(akn_uri, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.text

    def extract_document_number(self, uri: str) -> str:
        """
        Extract document number from Finlex URI
        e.g. .../2025/11017/fin -> 11017/2025
        """
        # Match pattern: .../year/number/...
        match = re.search(r"/(\d{4})/(\d+)/", uri)
        if match:
            _year, number = match.groups()
            return number
        return None
