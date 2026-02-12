"""
Cohere Reranker Service
Re-ranks search results using Cohere Rerank.
"""

import os

import cohere
from dotenv import load_dotenv

from src.config.logging_config import setup_logger
from src.utils.retry import with_retry

load_dotenv()
logger = setup_logger(__name__)


class CohereReranker:
    """
    Re-rank search results using Cohere.

    Default: rerank-v4.0-fast (low latency, multilingual, Finnish supported).
    Set COHERE_RERANK_MODEL to rerank-v4.0-pro for higher quality (slower).
    """

    def __init__(self, model: str | None = None):
        """Initialize Cohere client"""
        api_key = os.getenv("COHERE_API_KEY")
        if not api_key:
            raise ValueError("COHERE_API_KEY not found in environment")

        self.client = cohere.Client(api_key)
        # v4.0-fast: low latency; v4.0-pro: higher quality (slower)
        self.model = model or os.getenv("COHERE_RERANK_MODEL", "rerank-v4.0-fast").strip() or "rerank-v4.0-fast"
        logger.debug("Cohere Rerank initialized (model=%s)", self.model)

    @with_retry()
    def rerank(self, query: str, results: list[dict], top_k: int = 10) -> list[dict]:
        """
        Re-rank search results using Cohere.

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
        documents = []
        for result in results:
            doc_text = result.get("text") or result.get("chunk_text") or result.get("content") or ""
            documents.append(doc_text)

        # Call Cohere Rerank API (v4.0-fast for production latency)
        response = self.client.rerank(
            model=self.model,
            query=query,
            documents=documents,
            top_n=top_k,
        )

        # Map scores back to results
        reranked = []
        for item in response.results:
            result = results[item.index].copy()
            result["rerank_score"] = item.relevance_score
            reranked.append(result)

        return reranked
