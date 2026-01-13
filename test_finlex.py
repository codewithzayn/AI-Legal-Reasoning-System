#!/usr/bin/env python3
"""
Test NER processing time on a single document using spaCy
"""

import time
from src.services.finlex_api import FinlexAPI
from src.services.xml_parser import XMLParser


def main():
    print("NER PROCESSING TIME TEST (spaCy)")
    
    # Fetch a document
    print("\n1. Fetching document from Finlex...")
    api = FinlexAPI()
    doc = api.fetch_single_statute(year=2025)
    print(f"   ✓ Fetched: {doc['uri']}")
    
    # Parse XML
    print("\n2. Parsing XML...")
    parser = XMLParser()
    parsed = parser.parse(doc['xml'])
    print(parsed['text'])
    print(f"   ✓ Extracted {parsed['length']:,} characters")


if __name__ == "__main__":
    main()
