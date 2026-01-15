"""
Supabase Storage Service
Stores document chunks with embeddings in Supabase
"""

import os
from typing import List
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()


class SupabaseStorage:
    """
    Store document chunks with embeddings in Supabase
    
    Features:
    - Batch insert for efficiency
    - Automatic FTS vector generation (via trigger)
    - Error handling
    """
    
    def __init__(self, url: str = None, key: str = None):
        """
        Initialize Supabase client
        
        Args:
            url: Supabase URL (defaults to SUPABASE_URL env var)
            key: Supabase key (defaults to SUPABASE_KEY env var)
        """
        self.url = url or os.getenv("SUPABASE_URL")
        self.key = key or os.getenv("SUPABASE_KEY")
        
        if not self.url or not self.key:
            raise ValueError("Supabase URL and KEY required. Set SUPABASE_URL and SUPABASE_KEY env vars.")
        
        self.client: Client = create_client(self.url, self.key)
    
    def store_chunks(self, embedded_chunks: List) -> int:
        """
        Store embedded chunks in Supabase
        
        Args:
            embedded_chunks: List of EmbeddedChunk objects
            
        Returns:
            Number of chunks stored
        """
        # Prepare data for insertion
        rows = []
        for ec in embedded_chunks:
            rows.append({
                'document_uri': ec.metadata['document_uri'],
                'document_title': ec.metadata['document_title'],
                'document_year': ec.metadata['document_year'],
                'document_type': ec.metadata.get('document_type', 'unknown'),
                'document_category': ec.metadata.get('document_category', 'unknown'),
                'chunk_text': ec.text,
                'chunk_index': ec.chunk_index,
                'section_number': ec.section_number,
                'embedding': ec.embedding,
                'metadata': ec.metadata
            })
        
        # Upsert into Supabase (prevents duplicates via unique constraint)
        print(f"   Upserting {len(rows)} chunks into Supabase...")
        response = self.client.table('legal_chunks')\
            .upsert(rows, on_conflict='document_uri,chunk_index')\
            .execute()
        
        return len(response.data)
