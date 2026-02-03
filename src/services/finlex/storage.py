"""
Supabase Storage Service
Stores document chunks with embeddings in Supabase
"""

import os
from typing import List, Optional, Any
from supabase import create_client, Client
from dotenv import load_dotenv
from src.config.logging_config import setup_logger

load_dotenv()
logger = setup_logger(__name__)


class SupabaseStorage:
    """
    Store document chunks with embeddings in Supabase
    
    Features:
    - Batch insert for efficiency
    - Automatic FTS vector generation (via trigger)
    - Error handling
    """
    
    def __init__(self, url: Optional[str] = None, key: Optional[str] = None) -> None:
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
                'document_number': ec.metadata.get('document_number'),
                'language': ec.metadata.get('language', 'fin'),
                'chunk_text': ec.text,
                'chunk_index': ec.chunk_index,
                'section_number': ec.section_number,
                'embedding': ec.embedding,
                'metadata': ec.metadata
            })
        
        # Upsert into Supabase (prevents duplicates via unique constraint)
        logger.info(f"Upserting {len(rows)} chunks into Supabase...")
        response = self.client.table('legal_chunks')\
            .upsert(rows, on_conflict='document_uri,chunk_index')\
            .execute()
        
        return len(response.data)
    
    def log_failed_document(
        self, 
        document_uri: str, 
        error_message: str, 
        error_type: str = 'unknown', 
        document_category: Optional[str] = None,
        document_type: Optional[str] = None,
        document_year: Optional[int] = None,
        language: Optional[str] = None
    ) -> None:
        """
        Log a failed document to failed_documents table
        
        Args:
            document_uri: URI of failed document
            error_message: Error message
            error_type: Type of error (parse_error, api_error, embedding_error, storage_error)
            document_category: Document category
            document_type: Document type
            document_year: Document year
            language: Document language
        """
        try:
            # Check if already exists
            existing = self.client.table('failed_documents').select('id, retry_count').eq(
                'document_uri', document_uri
            ).execute()
            
            if existing.data:
                # Update retry count
                self.client.table('failed_documents').update({
                    'error_message': error_message,
                    'error_type': error_type,
                    'retry_count': existing.data[0]['retry_count'] + 1,
                    'last_retry_at': 'now()'
                }).eq('document_uri', document_uri).execute()
            else:
                # Insert new failure
                self.client.table('failed_documents').insert({
                    'document_uri': document_uri,
                    'document_category': document_category,
                    'document_type': document_type,
                    'document_year': document_year,
                    'language': language,
                    'error_message': error_message,
                    'error_type': error_type,
                    'retry_count': 0
                }).execute()
        except Exception as e:
            logger.error(f"Failed to log error: {e}")
