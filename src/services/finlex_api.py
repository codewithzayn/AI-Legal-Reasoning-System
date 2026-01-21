"""
Finlex Open Data API Client
"""

import requests
from typing import Dict


class FinlexAPI:
    """Client for Finlex Open Data API"""
    
    BASE_URL = "https://opendata.finlex.fi/finlex/avoindata/v1"
    
    def __init__(self):
        self.headers = {"User-Agent": "AI-Legal-Reasoning-System/1.0"}
    

    def get_document(self, uri: str) -> str:
        """Fetch XML document from URI"""
        response = requests.get(uri, headers=self.headers)
        response.raise_for_status()
        return response.text
    
    def _extract_document_type(self, uri: str) -> str:
        """Extract document type from Finlex URI"""
        parts = uri.split('/')
        try:
            category_idx = parts.index('fi') + 1
            type_idx = category_idx + 1
            return parts[type_idx]
        except (ValueError, IndexError):
            return "unknown"
    
    def _extract_year(self, uri: str) -> int:
        """Extract year from Finlex URI"""
        parts = uri.split('/')
        try:
            category_idx = parts.index('fi') + 1
            year_idx = category_idx + 2
            return int(parts[year_idx])
        except (ValueError, IndexError):
            return 0
    
    def _extract_document_category(self, uri: str) -> str:
        """Extract document category from Finlex URI (act, judgment, or doc)"""
        parts = uri.split('/')
        try:
            category_idx = parts.index('fi') + 1
            return parts[category_idx]  # act, judgment, or doc
        except (ValueError, IndexError):
            return "unknown"
    
    def fetch_single_statute(self, year: int = 2025) -> Dict[str, str]:
        """Fetch one statute for testing"""
        data = self.fetch_document_list(category="act", doc_type="statute", year=year, page=1, limit=1)
        # data is already a list
        if not data or len(data) == 0:
            raise ValueError(f"No statutes found for {year}")
        
        doc = data[0]
        xml = self.get_document(doc["akn_uri"])
        document_type = self._extract_document_type(doc["akn_uri"])
        document_category = self._extract_document_category(doc["akn_uri"])
        document_year = self._extract_year(doc["akn_uri"])
        return {
            "uri": doc["akn_uri"],
            "status": doc["status"],
            "document_type": document_type,
            "document_year": document_year,
            "document_category": document_category,
            "xml": xml
        }
    
    def fetch_document_list(self, category: str, doc_type: str, year: int, 
                           page: int = 1, limit: int = 10) -> list:
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
        
        params = {
            "startYear": year,
            "page": page,
            "limit": limit
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"API error: {str(e)}")
            return []
    
    def _extract_language(self, uri: str) -> str:
        """
        Extract language code from Finlex URI
        
        Args:
            uri: Finlex document URI
            
        Returns:
            Language code (fin, swe, eng)
        """
        if '/fin@' in uri:
            return 'fin'
        elif '/swe@' in uri:
            return 'swe'
        elif '/eng@' in uri:
            return 'eng'
        return 'fin'  # Default to Finnish
    
    def fetch_document_xml(self, akn_uri: str) -> str:
        """
        Fetch XML content for a document
        
        Args:
            akn_uri: Full Akoma Ntoso URI
            
        Returns:
            XML content as string
        """
        response = requests.get(akn_uri, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.text
