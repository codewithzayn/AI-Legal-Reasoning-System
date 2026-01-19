"""
BGE-Reranker Service
Re-ranks search results using BAAI/bge-reranker-v2-m3
"""

from typing import List, Dict
from sentence_transformers import CrossEncoder


class BGEReranker:
    """
    Re-rank search results using BGE cross-encoder
    
    Model: BAAI/bge-reranker-v2-m3 (multilingual)
    """
    
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        """Initialize BGE reranker model"""
        print(f"Loading BGE reranker: {model_name}...")
        self.model = CrossEncoder(model_name, max_length=512)
        print("✓ Model loaded")
    
    def rerank(
        self, 
        query: str, 
        results: List[Dict], 
        top_k: int = 10
    ) -> List[Dict]:
        """
        Re-rank search results
        
        Args:
            query: User query
            results: List of search results with 'chunk_text'
            top_k: Number of top results to return
            
        Returns:
            Re-ranked results with 'rerank_score'
        """
        if not results:
            return []
        
        # Prepare pairs for cross-encoder
        pairs = [[query, result['chunk_text']] for result in results]
        
        # Get scores
        scores = self.model.predict(pairs)
        
        # Add scores to results
        for result, score in zip(results, scores):
            result['rerank_score'] = float(score)
        
        # Sort by rerank score
        results.sort(key=lambda x: x['rerank_score'], reverse=True)
        
        return results[:top_k]
