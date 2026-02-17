# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL. Unauthorized copying, distribution, or use is strictly prohibited.

"""
Service Protocols (Interfaces)

Defines the contracts for key services so they can be mocked in tests and swapped
in production without coupling to concrete implementations.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.services.case_law.models import CaseLawDocument


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
@runtime_checkable
class RetrievalService(Protocol):
    """Contract for hybrid retrieval services.

    Any class that satisfies this protocol can be used as the retrieval backend
    in the agent pipeline (nodes.py) or anywhere else retrieval is needed.
    """

    async def vector_search(self, query_embedding: list[float], limit: int | None = None) -> list[dict]:
        """Semantic search using embedding vectors."""
        ...

    async def fts_search(self, query_text: str, limit: int | None = None) -> list[dict]:
        """Full-text keyword search."""
        ...

    def rrf_merge(
        self,
        vector_results: list[dict],
        fts_results: list[dict],
        k: int = 60,
    ) -> list[dict]:
        """Reciprocal Rank Fusion merge of two result sets."""
        ...

    async def hybrid_search(self, query_text: str, limit: int = 20) -> list[dict]:
        """Combined vector + FTS search with RRF merge."""
        ...

    async def hybrid_search_with_rerank(
        self,
        query_text: str,
        initial_limit: int = 20,
        final_limit: int = 10,
        response_lang: str | None = None,
        year_start: int | None = None,
        year_end: int | None = None,
    ) -> list[dict]:
        """Full retrieval pipeline: hybrid search → rerank → boost → diversity cap."""
        ...


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
@runtime_checkable
class StorageService(Protocol):
    """Contract for case-law storage backends.

    Any implementation that stores case-law documents and their sections
    (e.g. Supabase, local SQLite, in-memory stub) should satisfy this protocol.
    """

    def store_case(self, doc: CaseLawDocument) -> str | None:
        """Store a single case and return its UUID, or None on failure."""
        ...

    def store_cases(self, docs: list[CaseLawDocument]) -> int:
        """Store multiple cases. Return count of successfully stored cases."""
        ...

    def get_case_count(self, court_type: str | None = None, year: int | None = None) -> int:
        """Return the number of stored cases matching optional filters."""
        ...


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------
@runtime_checkable
class EmbeddingService(Protocol):
    """Contract for embedding generation.

    Any class that produces float-vector embeddings from text strings
    should satisfy this protocol.
    """

    def embed_query(self, query_text: str) -> list[float]:
        """Generate an embedding vector for a single query string."""
        ...

    def embed_chunks(self, chunks: list, batch_size: int = 100) -> list:
        """Generate embeddings for a batch of document chunks."""
        ...
