"""
Hybrid Retrieval Service
Combines vector search, full-text search, and RRF ranking
"""

import os
import re
import time
import asyncio
from typing import List, Dict, Optional
from supabase import create_async_client, AsyncClient, Client
from dotenv import load_dotenv
from src.services.common.embedder import DocumentEmbedder
from .reranker import CohereReranker
from src.config.logging_config import setup_logger
from src.config.settings import config

load_dotenv()
logger = setup_logger(__name__)


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
        
        self.client: Optional[AsyncClient] = None
        self.embedder = DocumentEmbedder()
        self.reranker = None
    
    async def _get_client(self) -> AsyncClient:
        """Lazy load async client"""
        if self.client is None:
            self.client = await create_async_client(self.url, self.key)
        return self.client
    
    def _get_reranker(self) -> CohereReranker:
        """Lazy load reranker (only when needed)"""
        if self.reranker is None:
            self.reranker = CohereReranker()
        return self.reranker
    
    async def vector_search(self, query_embedding: List[float], limit: int = None) -> List[Dict]:
        """
        Vector similarity search using cosine distance
        
        Args:
            query_embedding: Query embedding vector (1536-dim)
            limit: Number of results to return
            
        Returns:
            List of chunks with similarity scores
        """
        try:
            client = await self._get_client()
            response = await client.rpc(
                'vector_search',
                {
                    'query_embedding': query_embedding,
                    'match_threshold': config.MATCH_THRESHOLD,
                    'match_count': limit or config.VECTOR_SEARCH_TOP_K
                }
            ).execute()
            
            return response.data or []
        except Exception as e:
            logger.error(f"Vector search error: {e}")
            return []
    
    def _sanitize_fts_query(self, query: str) -> str:
        """Remove special characters that break to_tsquery"""
        # Remove special chars, keep only letters, numbers, spaces
        sanitized = re.sub(r'[^\w\s]', ' ', query)
        # Replace multiple spaces with single space
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        return sanitized
    
    async def fts_search(self, query_text: str, limit: int = None) -> List[Dict]:
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
            client = await self._get_client()
            response = await client.rpc(
                'fts_search',
                {
                    'query_text': sanitized_query,
                    'match_count': limit or config.FTS_SEARCH_TOP_K
                }
            ).execute()
            
            return response.data or []
        except Exception as e:
            logger.error(f"FTS search error: {e}")
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
    
    async def search_case_law(self, query_embedding: List[float], query_text: str, limit: int = None) -> List[Dict]:
        """
        Search case law using the specific SQL function (Hybrid internally)
        """
        try:
            # Sanitize query for FTS part of the internal function
            sanitized_query = self._sanitize_fts_query(query_text)
            
            client = await self._get_client()
            response = await client.rpc(
                'search_case_law',
                {
                    'query_embedding': query_embedding,
                    'query_text': sanitized_query,
                    'match_count': limit or config.VECTOR_SEARCH_TOP_K
                }
            ).execute()
            
            # Normalize to common format
            results = []
            for item in (response.data or []):
                results.append({
                    'id': item.get('section_id'),
                    'text': item.get('content', ''),
                    'source': 'case_law',
                    'metadata': {
                        'case_id': item.get('case_id'),
                        'court': item.get('court_type') or item.get('court'),
                        'year': item.get('case_year') or item.get('year'),
                        'type': item.get('section_type'),
                        'keywords': item.get('legal_domains', []),
                        'url': item.get('url')
                    },
                    'score': item.get('combined_score', 0)
                })
            return results
        except Exception as e:
            logger.error(f"Case law search error: {e}")
            return []

    async def hybrid_search(self, query_text: str, limit: int = 20) -> List[Dict]:
        """
        Global Hybrid Search: (Statutes Hybrid) + (Case Law Hybrid)
        """
        # Generate query embedding
        query_embedding = self.embedder.embed_query(query_text)
        
        # 1. Statutes Search (Vector + FTS via RRF)
        # We start independent tasks
        statute_vector_task = self.vector_search(query_embedding, limit=config.VECTOR_SEARCH_TOP_K)
        statute_fts_task = self.fts_search(query_text, limit=config.FTS_SEARCH_TOP_K)
        
        # 2. Case Law Search (Hybrid internally)
        case_law_task = self.search_case_law(query_embedding, query_text, limit=limit)
        
        # Run all concurrently
        stat_vec, stat_fts, case_results = await asyncio.gather(
            statute_vector_task, 
            statute_fts_task, 
            case_law_task
        )
        
        # Process Statute Results (Merge Vector + FTS)
        statute_results = self.rrf_merge(stat_vec, stat_fts)
        
        # Normalize Statute Results
        normalized_statutes = []
        for item in statute_results:
            normalized_statutes.append({
                'id': item['id'],
                'text': item.get('chunk_text', ''),
                'source': 'statute',
                'metadata': {
                    'title': item.get('document_title'),
                    'uri': item.get('document_uri'),
                    'section': item.get('section_number'),
                    'raw_metadata': item.get('metadata')
                },
                'score': item.get('rrf_score', 0)
            })
            
        # Combine all results
        # We assume Case Law results are already "good" candidates. 
        # We combine them and let the Re-ranker sort it out.
        combined_results = normalized_statutes + case_results
        
        return combined_results

    async def hybrid_search_with_rerank(
        self, 
        query_text: str, 
        initial_limit: int = 20,
        final_limit: int = 10
    ) -> List[Dict]:
        """
        Hybrid search + Cohere re-ranking
        """
        # Get initial results from hybrid search (Statutes + Case Law)
        # We ask for more initially to feed the reranker
        initial_results = await self.hybrid_search(query_text, limit=initial_limit)
        
        if not initial_results:
            return []

        # Re-rank with Cohere
        logger.info(f"[RERANK] Starting Cohere rerank on {len(initial_results)} results...")
        rerank_start = time.time()
        
        reranker = self._get_reranker()
        
        # Reranker expects a list of strings or dicts with 'text'
        # Our normalized results have 'text' key.
        # reranker.rerank needs to be robust to our new dict format
        reranked = reranker.rerank(query_text, initial_results, top_k=final_limit or config.RERANK_TOP_K)
        
        rerank_elapsed = time.time() - rerank_start
        logger.info(f"[RERANK] Completed in {rerank_elapsed:.2f}s - Top {len(reranked)} results")
        
        return reranked
