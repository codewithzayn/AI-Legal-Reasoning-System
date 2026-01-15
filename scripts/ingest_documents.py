#!/usr/bin/env python3
"""
Bulk Document Ingestion Script
Fetches multiple documents from Finlex and stores them in Supabase
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

from src.services.finlex_api import FinlexAPI
from src.services.xml_parser import XMLParser
from src.services.chunker import LegalDocumentChunker
from src.services.embedder import DocumentEmbedder
from src.services.supabase_storage import SupabaseStorage


def ingest_documents(year: int, limit: int = 10):
    """
    Ingest multiple documents from Finlex
    
    Args:
        year: Year to fetch documents from
        limit: Number of documents to fetch
    """
    print(f"\n{'='*70}")
    print(f"BULK DOCUMENT INGESTION - Year {year}, Limit {limit}")
    print(f"{'='*70}\n")
    
    # Initialize services
    api = FinlexAPI()
    parser = XMLParser()
    chunker = LegalDocumentChunker(max_chunk_size=1000, min_chunk_size=100, overlap=50)
    embedder = DocumentEmbedder()
    storage = SupabaseStorage()
    
    # Fetch document list
    print(f"1. Fetching document list from Finlex...")
    doc_list = api.get_statute_list(year=year, limit=limit)
    print(f"   ✓ Found {len(doc_list)} documents\n")
    
    total_chunks = 0
    successful = 0
    failed = 0
    
    # Process each document
    for idx, doc_info in enumerate(doc_list, 1):
        try:
            uri = doc_info['akn_uri']
            print(f"\n[{idx}/{len(doc_list)}] Processing: {uri}")
            
            # Fetch XML
            print(f"  → Fetching XML...")
            xml = api.get_document(uri)
            
            # Extract metadata
            document_type = api._extract_document_type(uri)
            document_category = api._extract_document_category(uri)
            document_year = api._extract_year(uri)
            
            # Parse XML
            print(f"  → Parsing XML...")
            parsed = parser.parse(xml)
            
            # Chunk document
            print(f"  → Chunking document...")
            chunks = chunker.chunk_document(
                text=parsed['text'],
                document_uri=uri,
                document_title=f"Document {idx}",
                document_year=document_year,
                document_type=document_type,
                document_category=document_category
            )
            print(f"  → Created {len(chunks)} chunks")
            
            # Generate embeddings
            print(f"  → Generating embeddings...")
            embedded_chunks = embedder.embed_chunks(chunks)
            
            # Store in Supabase
            print(f"  → Storing in Supabase...")
            stored = storage.store_chunks(embedded_chunks)
            print(f"  ✓ Stored {stored} chunks")
            
            total_chunks += stored
            successful += 1
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
            failed += 1
            continue
    
    # Summary
    print(f"INGESTION COMPLETE")
    print(f"Successful: {successful}/{len(doc_list)}")
    print(f"Failed: {failed}/{len(doc_list)}")
    print(f"Total chunks stored: {total_chunks}")


if __name__ == "__main__":
    # Default: Ingest 10 documents from 2025
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    
    ingest_documents(year=year, limit=limit)
