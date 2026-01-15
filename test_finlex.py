#!/usr/bin/env python3
"""
Test Finlex document processing pipeline:
Finlex API → XML Parser → Chunker → Embedder
"""

import time
from dotenv import load_dotenv
load_dotenv()

from src.services.finlex_api import FinlexAPI
from src.services.xml_parser import XMLParser
from src.services.chunker import LegalDocumentChunker
from src.services.embedder import DocumentEmbedder
from src.services.supabase_storage import SupabaseStorage


def main():
    print("FINLEX DOCUMENT PROCESSING PIPELINE TEST")
    
    # Step 1: Fetch document from Finlex
    print("\n1. Fetching document from Finlex API...")
    api = FinlexAPI()
    doc = api.fetch_single_statute(year=2024)
    # print(f"   ✓ Fetched: {doc['uri']}")
    
    # Step 2: Parse XML to extract text
    print("\n2. Parsing XML...")
    parser = XMLParser()
    parsed = parser.parse(doc['xml'])
    print(f"   ✓ Extracted {parsed['length']:,} characters")
    
    # Step 3: Chunk the document by § sections
    print("\n3. Chunking document by § sections...")
    chunker = LegalDocumentChunker(
        max_chunk_size=1000,
        min_chunk_size=100,
        overlap=50
    )
    chunks = chunker.chunk_document(
        text=parsed['text'],
        document_uri=doc['uri'],
        document_title=parsed['title'],
        document_year=doc['document_year'],
        document_type=doc['document_type']
    )
    print(f"   ✓ Created {len(chunks)} chunks")
    
    # Step 4: Creating chunks
    for i, chunk in enumerate(chunks[:3]):
        print(f"\nChunk {i+1}: {chunk.section_number}")
        print(f"  Words: {chunk.metadata['word_count']}")

    # Step 4: Generate embeddings
    print("\n4. Generating embeddings...")
    embedder = DocumentEmbedder()
    embedded_chunks = embedder.embed_chunks(chunks)
    print(f"   ✓ Generated {len(embedded_chunks)} embeddings")
    
    # Show results
    print("\nRESULTS")
    for i, ec in enumerate(embedded_chunks[:3]):
        print(f"\nChunk {i+1}: {ec.section_number}")
        print(f"  Words: {ec.metadata['word_count']}")
    
    # Step 5: Store in Supabase
    print("\n5. Storing in Supabase...")
    storage = SupabaseStorage()
    stored_count = storage.store_chunks(embedded_chunks)
    print(f"   ✓ Stored {stored_count} chunks in Supabase")
    
    print("\n✅ Complete pipeline test successful!")
    print("\nPipeline: Finlex API → XML Parser → Chunker → Embedder → Supabase ✅")


if __name__ == "__main__":
    main()
