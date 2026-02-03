"""
Embedding Service for Legal Document Chunks
Generates embeddings using OpenAI text-embedding-3-small
"""

import os
from typing import List, Dict
from openai import OpenAI
from dataclasses import dataclass
from src.config.logging_config import setup_logger
from src.config.settings import config
logger = setup_logger(__name__)


@dataclass
class EmbeddedChunk:
    """Chunk with embedding"""
    text: str
    embedding: List[float]
    chunk_index: int
    section_number: str
    metadata: Dict


class DocumentEmbedder:
    """
    Generate embeddings for document chunks using OpenAI
    
    Features:
    - Uses text-embedding-3-small (1536 dimensions)
    - Batch processing for efficiency
    - Error handling and retries
    """
    
    def __init__(self, api_key: str = None, model: str = None):
        """
        Initialize embedder
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Embedding model to use
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY env var or pass api_key parameter.")
        
        self.client = OpenAI(api_key=self.api_key)
        self.model = model or config.EMBEDDING_MODEL
        self.dimensions = config.EMBEDDING_DIMENSIONS
    
    def embed_chunks(self, chunks: List, batch_size: int = 100) -> List[EmbeddedChunk]:
        """
        Generate embeddings for chunks
        
        Args:
            chunks: List of Chunk objects from chunker
            batch_size: Number of chunks to process at once
            
        Returns:
            List of EmbeddedChunk objects with embeddings
        """
        embedded_chunks = []
        
        # Process in batches
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            
            # Extract texts
            texts = [chunk.text for chunk in batch]
            
            # Generate embeddings
            logger.info(f"Generating embeddings for batch {i//batch_size + 1} ({len(batch)} chunks)...")
            response = self.client.embeddings.create(
                model=self.model,
                input=texts
            )
            
            # Combine chunks with embeddings
            for chunk, embedding_obj in zip(batch, response.data):
                embedded_chunks.append(EmbeddedChunk(
                    text=chunk.text,
                    embedding=embedding_obj.embedding,
                    chunk_index=chunk.chunk_index,
                    section_number=chunk.section_number,
                    metadata=chunk.metadata
                ))
        
        return embedded_chunks
    
    def embed_query(self, query_text: str) -> List[float]:
        """
        Generate embedding for a single query
        
        Args:
            query_text: Query string
            
        Returns:
            Embedding vector (1536 dimensions)
        """
        response = self.client.embeddings.create(
            model=self.model,
            input=[query_text]
        )
        
        return response.data[0].embedding

    
    # def get_statistics(self, embedded_chunks: List[EmbeddedChunk]) -> Dict:
    #     """Get embedding statistics"""
    #     return {
    #         'total_embedded': len(embedded_chunks),
    #         'embedding_dimensions': len(embedded_chunks[0].embedding) if embedded_chunks else 0,
    #         'model': self.model
    #     }
