"""
Cohere Reranker Service
Re-ranks search results using Cohere Rerank v3
"""

import os
from typing import List, Dict
from dotenv import load_dotenv
import cohere
from src.config.logging_config import setup_logger

load_dotenv()
logger = setup_logger(__name__)


class CohereReranker:
    """
    Re-rank search results using Cohere Rerank v3
    
    Model: rerank-multilingual-v3.0 (supports Finnish)
    """
    
    def __init__(self):
        """Initialize Cohere client"""
        api_key = os.getenv("COHERE_API_KEY")
        if not api_key:
            raise ValueError("COHERE_API_KEY not found in environment")
        
        self.client = cohere.Client(api_key)
        logger.debug("Cohere Rerank initialized")
    
    def rerank(
        self, 
        query: str, 
        results: List[Dict], 
        top_k: int = 10
    ) -> List[Dict]:
        """
        Re-rank search results using Cohere
        
        Args:
            query: User query
            results: List of search results with 'chunk_text'
            top_k: Number of top results to return
            
        Returns:
            Re-ranked results with 'rerank_score'
        """
        if not results:
            return []
        
        # Prepare documents for Cohere
        documents = [result['chunk_text'] for result in results]
        
        # Call Cohere Rerank API
        response = self.client.rerank(
            model="rerank-v4.0-fast",
            query=query,
            documents=documents,
            top_n=top_k
        )
        
        # Map scores back to results
        reranked = []
        for item in response.results:
            result = results[item.index].copy()
            result['rerank_score'] = item.relevance_score
            reranked.append(result)
        
        return reranked
