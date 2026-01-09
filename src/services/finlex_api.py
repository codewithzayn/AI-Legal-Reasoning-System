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
    
    def get_statute_list(self, year: int = 2025, limit: int = 1) -> Dict:
        """Get list of statutes"""
        url = f"{self.BASE_URL}/akn/fi/act/statute/list"
        
        params = {
            "langAndVersion": "fin@",
            "startYear": year,
            "endYear": year,
            "limit": limit,
            "page": 1
        }
        
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()
    
    def get_document(self, uri: str) -> str:
        """Fetch XML document from URI"""
        response = requests.get(uri, headers=self.headers)
        response.raise_for_status()
        return response.text
    
    def fetch_single_statute(self, year: int = 2025) -> Dict[str, str]:
        """Fetch one statute for testing"""
        data = self.get_statute_list(year=year, limit=1)
        # data is already a list
        if not data or len(data) == 0:
            raise ValueError(f"No statutes found for {year}")
        
        doc = data[0]
        xml = self.get_document(doc["akn_uri"])
        return {
            "uri": doc["akn_uri"],
            "status": doc["status"],
            "xml": xml
        }
