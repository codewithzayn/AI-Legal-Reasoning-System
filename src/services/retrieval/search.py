"""
Hybrid Retrieval Service
Combines vector search, full-text search, RRF ranking,
multi-query expansion, and direct case-ID lookup.
"""

import asyncio
import os
import re
import time

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from supabase import AsyncClient, create_async_client

from src.config.logging_config import setup_logger
from src.config.settings import config
from src.services.common.embedder import DocumentEmbedder

from .reranker import CohereReranker

load_dotenv()
logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# Regex to detect case IDs like KKO:2022:18, KHO:2023:5, etc. in user query
# ---------------------------------------------------------------------------
_CASE_ID_RE = re.compile(r"\b(KKO|KHO)\s*:\s*(\d{4})\s*:\s*(\d+)\b", re.IGNORECASE)

_expansion_llm = None

def _get_expansion_llm():
    global _expansion_llm
    if _expansion_llm is None:
        _expansion_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.4)
    return _expansion_llm


class HybridRetrieval:
    """
    Hybrid search combining vector similarity and full-text search

    Methods:
    - vector_search: Semantic search using embeddings
    - fts_search: Keyword search using PostgreSQL ts_rank
    - rrf_merge: Reciprocal Rank Fusion to combine results
    - hybrid_search: Orchestrates all methods
    - expand_query: Multi-query expansion via LLM
    - fetch_case_chunks: Direct case-ID lookup (bypasses vector search)
    """

    def __init__(self, url: str = None, key: str = None):
        """Initialize Supabase client and embedder"""
        self.url = url or os.getenv("SUPABASE_URL")
        self.key = key or os.getenv("SUPABASE_KEY")

        if not self.url or not self.key:
            raise ValueError("Supabase URL and KEY required")

        self.client: AsyncClient | None = None
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

    # ------------------------------------------------------------------
    # Multi-query expansion
    # ------------------------------------------------------------------
    @staticmethod
    async def expand_query(query: str) -> list[str]:
        """Generate 2 alternative query formulations to improve recall.

        Uses gpt-4o-mini to rephrase the user's question into different
        angles / synonyms.  Returns a list of 2 alternative queries
        (the original query is always used separately).
        """
        system_prompt = (
            "You are a Finnish legal search expert. Given a user question, "
            "generate exactly 2 alternative search queries in Finnish that "
            "capture the same legal meaning using different phrasing, synonyms, "
            "or legal terminology.\n\n"
            "Rules:\n"
            "- Each alternative must be on its own line.\n"
            "- Output ONLY the 2 alternative queries, nothing else.\n"
            "- Keep queries concise (max ~20 words each).\n"
            "- If the question references a specific case (e.g. KKO:2022:18), "
            "include that reference in at least one alternative."
        )
        try:
            response = await _get_expansion_llm().ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=query)])
            lines = [ln.strip().lstrip("0123456789.-) ") for ln in response.content.strip().splitlines() if ln.strip()]
            # Return at most 2 alternatives
            alternatives = [ln for ln in lines if ln][:2]
            if alternatives:
                logger.info("Multi-query expansion → %s alternatives", len(alternatives))
                for i, alt in enumerate(alternatives):
                    logger.info("  alt-%s: %s", i + 1, alt)
            return alternatives
        except Exception as e:
            logger.warning("Multi-query expansion failed (non-critical): %s", e)
            return []

    # ------------------------------------------------------------------
    # Direct case-ID lookup
    # ------------------------------------------------------------------
    @staticmethod
    def extract_case_ids(query: str) -> list[str]:
        """Extract case IDs (e.g. KKO:2022:18) mentioned in the query."""
        matches = _CASE_ID_RE.findall(query)
        # Each match is (court, year, number) — normalize to uppercase
        return [f"{court.upper()}:{year}:{number}" for court, year, number in matches]

    async def fetch_case_chunks(self, case_id: str) -> list[dict]:
        """Fetch ALL chunks for a specific case_id directly from Supabase.
        This bypasses vector search entirely — guarantees we have the
        document's content when the user references it by ID."""
        try:
            client = await self._get_client()
            response = (
                await client.table("case_law_sections")
                .select("id, content, section_type, section_title, case_law_id")
                .eq(
                    "case_law_id",
                    (await client.table("case_law").select("id").eq("case_id", case_id).limit(1).execute()).data[0][
                        "id"
                    ],
                )
                .execute()
            )

            # Also get case metadata for the normalized format
            case_meta = (
                await client.table("case_law")
                .select("case_id, court_type, case_year, legal_domains, url")
                .eq("case_id", case_id)
                .limit(1)
                .execute()
            )
            meta_row = case_meta.data[0] if case_meta.data else {}

            results = []
            for item in response.data or []:
                results.append(
                    {
                        "id": item["id"],
                        "text": item.get("content", ""),
                        "source": "case_law",
                        "metadata": {
                            "case_id": meta_row.get("case_id", case_id),
                            "court": meta_row.get("court_type"),
                            "year": meta_row.get("case_year"),
                            "type": item.get("section_type"),
                            "keywords": meta_row.get("legal_domains", []),
                            "url": meta_row.get("url"),
                        },
                        "score": 1.0,  # max score for direct lookup
                    }
                )
            logger.info("Direct case lookup → %s chunks for %s", len(results), case_id)
            return results
        except Exception as e:
            logger.warning("Direct case lookup failed for %s: %s", case_id, e)
            return []

    # ------------------------------------------------------------------
    # Core search methods
    # ------------------------------------------------------------------
    async def vector_search(self, query_embedding: list[float], limit: int = None) -> list[dict]:
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
                "vector_search",
                {
                    "query_embedding": query_embedding,
                    "match_threshold": config.MATCH_THRESHOLD,
                    "match_count": limit or config.VECTOR_SEARCH_TOP_K,
                },
            ).execute()

            return response.data or []
        except Exception as e:
            logger.error(f"Vector search error: {e}")
            return []

    def _sanitize_fts_query(self, query: str) -> str:
        """Remove special characters that break to_tsquery"""
        # Remove special chars, keep only letters, numbers, spaces
        sanitized = re.sub(r"[^\w\s]", " ", query)
        # Replace multiple spaces with single space
        sanitized = re.sub(r"\s+", " ", sanitized).strip()
        return sanitized

    async def fts_search(self, query_text: str, limit: int = None) -> list[dict]:
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
                "fts_search", {"query_text": sanitized_query, "match_count": limit or config.FTS_SEARCH_TOP_K}
            ).execute()

            return response.data or []
        except Exception as e:
            logger.error(f"FTS search error: {e}")
            return []

    def rrf_merge(self, vector_results: list[dict], fts_results: list[dict], k: int = 60) -> list[dict]:
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
        vector_ranks = {item["id"]: rank + 1 for rank, item in enumerate(vector_results)}
        fts_ranks = {item["id"]: rank + 1 for rank, item in enumerate(fts_results)}

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
            if item["id"] not in chunks_map:
                chunks_map[item["id"]] = item

        # Create merged results with RRF scores
        merged = []
        for chunk_id, rrf_score in rrf_scores.items():
            chunk = chunks_map[chunk_id].copy()
            chunk["rrf_score"] = rrf_score
            chunk["vector_rank"] = vector_ranks.get(chunk_id)
            chunk["fts_rank"] = fts_ranks.get(chunk_id)
            merged.append(chunk)

        # Sort by RRF score (descending)
        merged.sort(key=lambda x: x["rrf_score"], reverse=True)

        return merged

    async def search_case_law(self, query_embedding: list[float], query_text: str, limit: int = None) -> list[dict]:
        """
        Search case law using the specific SQL function (Hybrid internally)
        """
        try:
            # Sanitize query for FTS part of the internal function
            sanitized_query = self._sanitize_fts_query(query_text)

            client = await self._get_client()
            response = await client.rpc(
                "search_case_law",
                {
                    "query_embedding": query_embedding,
                    "query_text": sanitized_query,
                    "match_count": limit or config.VECTOR_SEARCH_TOP_K,
                },
            ).execute()

            # Normalize to common format
            results = []
            for item in response.data or []:
                results.append(
                    {
                        "id": item.get("section_id"),
                        "text": item.get("content", ""),
                        "source": "case_law",
                        "metadata": {
                            "case_id": item.get("case_id"),
                            "court": item.get("court_type") or item.get("court"),
                            "year": item.get("case_year") or item.get("year"),
                            "type": item.get("section_type"),
                            "keywords": item.get("legal_domains", []),
                            "url": item.get("url"),
                        },
                        "score": item.get("combined_score", 0),
                    }
                )
            return results
        except Exception as e:
            logger.error(f"Case law search error: {e}")
            return []

    async def hybrid_search(self, query_text: str, limit: int = 20) -> list[dict]:
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
        stat_vec, stat_fts, case_results = await asyncio.gather(statute_vector_task, statute_fts_task, case_law_task)

        # Process Statute Results (Merge Vector + FTS)
        statute_results = self.rrf_merge(stat_vec, stat_fts)

        # Normalize Statute Results
        normalized_statutes = []
        for item in statute_results:
            normalized_statutes.append(
                {
                    "id": item["id"],
                    "text": item.get("chunk_text", ""),
                    "source": "statute",
                    "metadata": {
                        "title": item.get("document_title"),
                        "uri": item.get("document_uri"),
                        "section": item.get("section_number"),
                        "raw_metadata": item.get("metadata"),
                    },
                    "score": item.get("rrf_score", 0),
                }
            )

        # Combine all results
        # We assume Case Law results are already "good" candidates.
        # We combine them and let the Re-ranker sort it out.
        combined_results = normalized_statutes + case_results

        return combined_results

    # ------------------------------------------------------------------
    # Multi-query hybrid search
    # ------------------------------------------------------------------
    async def _multi_query_hybrid_search(self, query_text: str, limit: int = 20) -> list[dict]:
        """Run hybrid search with the original query AND 2 LLM-generated
        alternative queries, then merge all results (deduplicated by chunk id).

        This dramatically improves recall: chunks that one query formulation
        misses may be captured by another formulation.
        """
        # 1. Generate alternative queries in parallel with the original search
        expansion_task = self.expand_query(query_text)
        original_search_task = self.hybrid_search(query_text, limit=limit)

        alternatives, original_results = await asyncio.gather(expansion_task, original_search_task)

        if not alternatives:
            return original_results

        # 2. Run hybrid search for each alternative query concurrently
        alt_tasks = [self.hybrid_search(alt_q, limit=limit) for alt_q in alternatives]
        alt_results_list = await asyncio.gather(*alt_tasks)

        # 3. Merge all results, keeping the highest score per chunk id
        seen: dict[str, dict] = {}
        for result in original_results:
            rid = result["id"]
            if rid not in seen or result.get("score", 0) > seen[rid].get("score", 0):
                seen[rid] = result

        for alt_results in alt_results_list:
            for result in alt_results:
                rid = result["id"]
                if rid not in seen or result.get("score", 0) > seen[rid].get("score", 0):
                    seen[rid] = result

        merged = sorted(seen.values(), key=lambda x: x.get("score", 0), reverse=True)
        logger.info(
            "Multi-query merge → %s unique chunks (original=%s, alternatives=%s)",
            len(merged),
            len(original_results),
            sum(len(r) for r in alt_results_list),
        )
        return merged

    # ------------------------------------------------------------------
    # Main entry point: hybrid search + case-ID boost + multi-query + rerank
    # ------------------------------------------------------------------
    async def hybrid_search_with_rerank(
        self, query_text: str, initial_limit: int = 20, final_limit: int = 10
    ) -> list[dict]:
        """
        Full retrieval pipeline:
        1. Detect explicit case IDs in the query → fetch their chunks directly
        2. Run multi-query hybrid search (original + 2 alternatives)
        3. Merge direct-lookup chunks with search results (deduplicated)
        4. Rerank with Cohere
        5. Return top final_limit chunks to LLM
        """
        # --- Step 1: Direct case-ID lookup ---
        mentioned_ids = self.extract_case_ids(query_text)
        direct_chunks: list[dict] = []
        if mentioned_ids:
            logger.info("Detected case IDs in query: %s", mentioned_ids)
            direct_tasks = [self.fetch_case_chunks(cid) for cid in mentioned_ids]
            direct_results = await asyncio.gather(*direct_tasks)
            for chunks in direct_results:
                direct_chunks.extend(chunks)

        # --- Step 2: Search (multi-query if enabled, otherwise single query) ---
        if config.MULTI_QUERY_ENABLED:
            search_results = await self._multi_query_hybrid_search(query_text, limit=initial_limit)
        else:
            search_results = await self.hybrid_search(query_text, limit=initial_limit)

        # --- Step 3: Merge direct chunks + search results (dedup by id) ---
        seen_ids: set[str] = set()
        combined: list[dict] = []

        # Direct-lookup chunks go first (guaranteed relevant)
        for chunk in direct_chunks:
            cid = chunk["id"]
            if cid not in seen_ids:
                seen_ids.add(cid)
                combined.append(chunk)

        for chunk in search_results:
            cid = chunk["id"]
            if cid not in seen_ids:
                seen_ids.add(cid)
                combined.append(chunk)

        if not combined:
            return []

        # Log retrieved candidates before rerank (for debugging relevancy)
        logger.info(
            "Retrieved %s candidates (direct=%s, search=%s):", len(combined), len(direct_chunks), len(search_results)
        )
        for i, r in enumerate(combined[:20]):
            src = r.get("source", "?")
            score = r.get("score", 0)
            meta = r.get("metadata", {})
            label = meta.get("case_id") or meta.get("title") or meta.get("uri") or "?"
            logger.info("  [%s] %s | %s | score=%.4f", i + 1, src, label, score)

        # --- Step 4: Rerank with Cohere ---
        logger.info("Reranking...")
        rerank_start = time.time()
        reranker = self._get_reranker()
        top_k = final_limit if final_limit is not None else config.CHUNKS_TO_LLM
        reranked = reranker.rerank(query_text, combined, top_k=top_k)
        rerank_elapsed = time.time() - rerank_start
        logger.info("Rerank done → top %s in %.1fs", len(reranked), rerank_elapsed)

        # Log final reranked results (what the LLM will see)
        logger.info("Final results sent to LLM:")
        for i, r in enumerate(reranked):
            src = r.get("source", "?")
            score = r.get("score", 0)
            meta = r.get("metadata", {})
            label = meta.get("case_id") or meta.get("title") or meta.get("uri") or "?"
            logger.info("  [%s] %s | %s | score=%.4f", i + 1, src, label, score)

        return reranked
