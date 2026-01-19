"""
Hybrid Retrieval Service
Combines vector search, full-text search, and RRF ranking
"""

import os
import re
import time
from typing import List, Dict, Optional
from supabase import create_client, Client
from dotenv import load_dotenv
from .embedder import DocumentEmbedder
from .reranker import CohereReranker

load_dotenv()


class HybridRetrieval:
    """
    Hybrid search combining vector similarity and full-text search
    
    Methods:
    - vector_search: Semantic search using embeddings
    - fts_search: Keyword search using PostgreSQL ts_rank
    - rrf_merge: Reciprocal Rank Fusion to combine results
    - hybrid_search: Orchestrates all methods
    """
    
    def __init__(self, url: str = None, key: str = None):
        """Initialize Supabase client and embedder"""
        self.url = url or os.getenv("SUPABASE_URL")
        self.key = key or os.getenv("SUPABASE_KEY")
        
        if not self.url or not self.key:
            raise ValueError("Supabase URL and KEY required")
        
        self.client: Client = create_client(self.url, self.key)
        self.embedder = DocumentEmbedder()
        self.reranker = None
    
    def _get_reranker(self) -> CohereReranker:
        """Lazy load reranker (only when needed)"""
        if self.reranker is None:
            self.reranker = CohereReranker()
        return self.reranker
    
    def vector_search(self, query_embedding: List[float], limit: int = 50) -> List[Dict]:
        """
        Vector similarity search using cosine distance
        
        Args:
            query_embedding: Query embedding vector (1536-dim)
            limit: Number of results to return
            
        Returns:
            List of chunks with similarity scores
        """
        try:
            response = self.client.rpc(
                'vector_search',
                {
                    'query_embedding': query_embedding,
                    'match_threshold': 0.3,
                    'match_count': limit
                }
            ).execute()
            
            return response.data or []
        except Exception as e:
            print(f"Vector search error: {e}")
            return []
    
    def _sanitize_fts_query(self, query: str) -> str:
        """Remove special characters that break to_tsquery"""
        # Remove special chars, keep only letters, numbers, spaces
        sanitized = re.sub(r'[^\w\s]', ' ', query)
        # Replace multiple spaces with single space
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        return sanitized
    
    def fts_search(self, query_text: str, limit: int = 50) -> List[Dict]:
        """
        Full-text search using PostgreSQL ts_rank
        
        Args:
            query_text: Search query in Finnish
            limit: Number of results to return
            
        Returns:
            List of chunks with relevance scores
        """
        try:
            # Sanitize query for FTS
            sanitized_query = self._sanitize_fts_query(query_text)
            
            response = self.client.rpc(
                'fts_search',
                {
                    'query_text': sanitized_query,
                    'match_count': limit
                }
            ).execute()
            
            return response.data or []
        except Exception as e:
            print(f"FTS search error: {e}")
            return []
    
    def rrf_merge(
        self, 
        vector_results: List[Dict], 
        fts_results: List[Dict], 
        k: int = 60
    ) -> List[Dict]:
        """
        Reciprocal Rank Fusion (RRF) to merge search results
        
        Formula: RRF_score = 1/(k + rank_vector) + 1/(k + rank_fts)
        
        Args:
            vector_results: Results from vector search
            fts_results: Results from FTS
            k: Constant to prevent division by zero (default: 60)
            
        Returns:
            Merged and re-ranked results
        """
        # Create rank maps
        vector_ranks = {item['id']: rank + 1 for rank, item in enumerate(vector_results)}
        fts_ranks = {item['id']: rank + 1 for rank, item in enumerate(fts_results)}
        
        # Collect all unique chunk IDs
        all_ids = set(vector_ranks.keys()) | set(fts_ranks.keys())
        
        # Calculate RRF scores
        rrf_scores = {}
        for chunk_id in all_ids:
            vector_rank = vector_ranks.get(chunk_id, 0)
            fts_rank = fts_ranks.get(chunk_id, 0)
            
            # RRF formula
            score = 0.0
            if vector_rank > 0:
                score += 1.0 / (k + vector_rank)
            if fts_rank > 0:
                score += 1.0 / (k + fts_rank)
            
            rrf_scores[chunk_id] = score
        
        # Get full chunk data (prefer vector results, fallback to FTS)
        chunks_map = {}
        for item in vector_results + fts_results:
            if item['id'] not in chunks_map:
                chunks_map[item['id']] = item
        
        # Create merged results with RRF scores
        merged = []
        for chunk_id, rrf_score in rrf_scores.items():
            chunk = chunks_map[chunk_id].copy()
            chunk['rrf_score'] = rrf_score
            chunk['vector_rank'] = vector_ranks.get(chunk_id, None)
            chunk['fts_rank'] = fts_ranks.get(chunk_id, None)
            merged.append(chunk)
        
        # Sort by RRF score (descending)
        merged.sort(key=lambda x: x['rrf_score'], reverse=True)
        
        return merged
    
    def hybrid_search(self, query_text: str, limit: int = 20) -> List[Dict]:
        """
        Hybrid search: Vector + FTS + RRF
        
        Args:
            query_text: User query in Finnish
            limit: Number of final results to return
            
        Returns:
            Top ranked chunks with metadata
        """
        # Generate query embedding
        query_embedding = self.embedder.embed_query(query_text)
        
        # Perform both searches
        vector_results = self.vector_search(query_embedding, limit=50)
        fts_results = self.fts_search(query_text, limit=50)
        # Merge with RRF
        merged_results = self.rrf_merge(vector_results, fts_results)
        
        # Return top N
        return merged_results[:limit]
    
    def hybrid_search_with_rerank(
        self, 
        query_text: str, 
        initial_limit: int = 20,
        final_limit: int = 10
    ) -> List[Dict]:
        """
        Hybrid search + Cohere re-ranking
        
        Args:
            query_text: User query
            initial_limit: Results before re-ranking
            final_limit: Results after re-ranking
            
        Returns:
            Re-ranked top results
        """
        # Get initial results from hybrid search
        initial_results = self.hybrid_search(query_text, limit=initial_limit)
        
        # Re-rank with Cohere
        print(f"⏱️  [RERANK] Starting Cohere rerank on {len(initial_results)} results...")
        rerank_start = time.time()
        
        reranker = self._get_reranker()
        reranked = reranker.rerank(query_text, initial_results, top_k=final_limit)
        
        rerank_elapsed = time.time() - rerank_start
        print(f"✅ [RERANK] Completed in {rerank_elapsed:.2f}s - Top {len(reranked)} results")
        
        return reranked
