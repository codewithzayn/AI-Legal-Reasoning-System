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
        self._client_lock = asyncio.Lock()
        self.embedder = DocumentEmbedder()
        self.reranker = None

    async def _get_client(self) -> AsyncClient:
        """Lazy load async client (thread-safe for concurrent requests)."""
        async with self._client_lock:
            if self.client is None:
                self.client = await create_async_client(self.url, self.key)
        return self.client

    def _get_reranker(self) -> CohereReranker:
        """Lazy load reranker (only when needed)"""
        if self.reranker is None:
            self.reranker = CohereReranker()
        return self.reranker

    # ------------------------------------------------------------------
    # Multi-query expansion (legal-focused)
    # ------------------------------------------------------------------
    @staticmethod
    async def expand_query(query: str) -> list[str]:
        """Generate 2 targeted legal query variants for better recall."""
        system_prompt = """Olet suomalaisen oikeuden hakuasiantuntija. Luo kaksi vaihtoehtoista hakukyselyä.

Luo:
1. **Lakitekninen versio**: Käytä lakipykäliä, virallisia termejä (edellytykset, soveltamisala, toimivalta, vastuu)
2. **Tapausperusteinen versio**: Mitä tosiasiallisia tilanteita tai kysymyksiä tämä koskee?

Säännöt:
- Pidä pykäläviittaukset (esim. OYL 5:21, RL 10:3)
- Jos kysymys on "milloin/missä tapauksessa", varmista että molemmat versiot etsivät EDELLYTYKSIÄ
- Vastaa VAIN kahdella kyselyllä, yksi per rivi
- Älä selitä

Esimerkki:
Alkuperäinen: "Milloin yhtiökokous voidaan määrätä pidettäväksi?"
1. OYL yhtiökokouksen määrääminen tuomioistuimen päätöksellä edellytykset
2. Millä perusteella tuomioistuin voi velvoittaa yhtiön kutsumaan koolle yhtiökokouksen"""
        try:
            response = await _get_expansion_llm().ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=f"Alkuperäinen: {query}"),
                ]
            )
            lines = [ln.strip().lstrip("0123456789.-) ") for ln in response.content.strip().splitlines() if ln.strip()]
            alternatives = [ln for ln in lines if ln][:2]
            if alternatives:
                logger.info("Multi-query expansion → %s alternatives", len(alternatives))
                for i, alt in enumerate(alternatives, 1):
                    logger.info("  alt-%s: %s", i, alt)
            return alternatives
        except Exception as e:
            logger.warning("Multi-query expansion failed (non-critical): %s", e)
            return []

    # ------------------------------------------------------------------
    # Query classification and exact-match boost
    # ------------------------------------------------------------------
    @staticmethod
    def _classify_query(query: str) -> str:
        """Classify query type to adjust retrieval strategy."""
        query_lower = query.lower()
        # Statute: abbreviation (RL 10:3) or Finnish form (10 luvun 3 §)
        if re.search(r"\b(OYL|RL|OK|VML|SOL|SotOikL)\s*\d+:\d+", query, re.IGNORECASE):
            return "statute_interpretation"
        if re.search(r"\d+\s+luvun\s+\d+\s*§", query_lower):
            return "statute_interpretation"
        # Conditions: milloin, edellytykset, or any form of "edellyty" (edellytyksillä, edellytyksiä, ...)
        if any(w in query_lower for w in ["milloin", "missä tapauksessa"]) or "edellyty" in query_lower:
            return "conditions"
        if any(w in query_lower for w in ["toimivalta", "tuomioistuin", "käsittelee", "menettely"]):
            return "jurisdiction"
        if any(w in query_lower for w in ["vastuu", "vastuussa", "korvaus", "vahingonkorvaus"]):
            return "liability"
        return "general"

    def _compute_exact_match_boost(self, chunk: dict, query: str) -> float:
        """Boost chunks with exact statute/case ID matches to the query."""
        boost = 1.0
        text = (chunk.get("text") or chunk.get("chunk_text") or chunk.get("content") or "").lower()
        query_lower = query.lower()
        # Abbreviation style: RL 10:3, OYL 5:21
        statute_pattern = r"\b(OYL|RL|OK|VML|SOL|SotOikL)\s*\d+:\d+\b"
        query_statutes = set(re.findall(statute_pattern, query, re.IGNORECASE))
        chunk_statutes = set(re.findall(statute_pattern, text, re.IGNORECASE))
        if query_statutes & chunk_statutes:
            boost *= 2.0
        # Finnish style: "10 luvun 3 §", "rikoslain 10 luvun 3 §" — boost if chunk discusses same chapter/section
        luku_para = re.findall(r"(\d+)\s+luvun\s+(\d+)\s*§", query_lower)
        if luku_para:
            for ch, sec in luku_para:
                if re.search(
                    rf"\b{ch}\s+luvun\s+{sec}\b|\b{ch}\s+§\s*:\s*{sec}\b|chapter\s+{ch}.*section\s+{sec}",
                    text,
                    re.IGNORECASE,
                ):
                    boost *= 2.0
                    break
        # Subsection (kohta): e.g. "3 §:n 3 kohdan" — extra boost when chunk contains same provision + subsection
        kohta_match = re.search(r"(?:\d+\s+luvun\s+\d+\s*§[^\d]*)?(\d+)\s+kohd(?:an|a)\b", query_lower)
        if kohta_match:
            kohta_num = kohta_match.group(1)
            if re.search(r"\d+\s+luvun\s+\d+\s*§", text) and re.search(rf"\b{kohta_num}\s+kohd(?:an|a)\b", text):
                boost *= 1.8
        case_ids = self.extract_case_ids(query)
        chunk_case_id = ((chunk.get("metadata") or {}).get("case_id") or "").upper()
        if case_ids and chunk_case_id in [c.upper() for c in case_ids]:
            boost *= 1.5

        # For "conditions" queries (milloin / edellyty* / missä tapauksessa): boost reasoning and conditions language
        is_conditions_query = (
            any(w in query_lower for w in ["milloin", "missä tapauksessa"]) or "edellyty" in query_lower
        )
        if is_conditions_query:
            meta = chunk.get("metadata") or {}
            section_type = (meta.get("type") or meta.get("section_type") or "").lower()
            section_title = (meta.get("section_title") or chunk.get("section_title") or "").lower()
            if section_type in ("reasoning", "perustelut") or "perustelut" in section_title:
                boost *= 1.4
            conditions_words = [
                "jos",
                "kun",
                "saattaa todennäköiseksi",
                "on myönnettävä",
                "voi jäädä",
                "lopulliseksi",
                "riittämättömiksi",
                "näin on asia",
            ]
            conditions_matches = sum(1 for w in conditions_words if w in text)
            if conditions_matches >= 3:
                boost *= 1.3

        # General keyword matching: boost if chunk contains many query terms
        stopwords = {
            "milloin",
            "mitä",
            "miten",
            "miksi",
            "missä",
            "voiko",
            "voidaan",
            "onko",
            "oliko",
            "pitää",
            "täytyy",
            "kuuluu",
            "mukaan",
            "että",
        }
        query_words = set(word for word in query_lower.split() if len(word) >= 4 and word not in stopwords)
        if query_words:
            matches = sum(1 for word in query_words if word in text)
            match_ratio = matches / len(query_words)
            if match_ratio >= 0.5:
                boost *= 1 + match_ratio * 0.5  # Up to 1.75x for 100% match

        return boost

    def _rrf_blend_scores(self, reranked: list[dict], k: int = 60) -> list[dict]:
        """Blend rerank and pre-rerank (RRF) using RRF formula instead of weighted average."""
        rerank_ranks = {
            r["id"]: i + 1 for i, r in enumerate(sorted(reranked, key=lambda x: x.get("rerank_score", 0), reverse=True))
        }
        rrf_ranks = {
            r["id"]: i + 1 for i, r in enumerate(sorted(reranked, key=lambda x: x.get("score", 0), reverse=True))
        }
        for r in reranked:
            rid = r["id"]
            rerank_rrf = 1.0 / (k + rerank_ranks.get(rid, 999))
            rrf_rrf = 1.0 / (k + rrf_ranks.get(rid, 999))
            r["blended_score"] = rerank_rrf + rrf_rrf
        return sorted(reranked, key=lambda x: x.get("blended_score", 0), reverse=True)

    @staticmethod
    def _smart_diversity_cap(results: list[dict], max_per_case: int = 3, top_k: int = 15) -> list[dict]:
        """Keep top 2 chunks uncapped, then apply per-case cap for the rest."""
        if len(results) <= 2:
            return results[:top_k]
        output = list(results[:2])
        case_counts: dict[str, int] = {}
        for r in output:
            cid = (r.get("metadata") or {}).get("case_id") or ""
            case_counts[cid] = case_counts.get(cid, 0) + 1
        for r in results[2:]:
            if len(output) >= top_k:
                break
            cid = (r.get("metadata") or {}).get("case_id") or ""
            if case_counts.get(cid, 0) < max_per_case:
                output.append(r)
                case_counts[cid] = case_counts.get(cid, 0) + 1
        return output

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
    async def hybrid_search_with_rerank(  # noqa: C901, PLR0912, PLR0915
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
        # --- Step 1 & 2: Direct lookup + Search in parallel (when both apply) ---
        mentioned_ids = self.extract_case_ids(query_text)
        direct_chunks: list[dict] = []
        search_results: list[dict] = []

        async def _do_direct():
            if not mentioned_ids:
                return []
            logger.info("Detected case IDs in query: %s", mentioned_ids)
            direct_tasks = [self.fetch_case_chunks(cid) for cid in mentioned_ids]
            direct_results = await asyncio.gather(*direct_tasks)
            out = []
            for chunks in direct_results:
                out.extend(chunks)
            return out

        async def _do_search():
            if config.MULTI_QUERY_ENABLED:
                return await self._multi_query_hybrid_search(query_text, limit=initial_limit)
            return await self.hybrid_search(query_text, limit=initial_limit)

        direct_chunks, search_results = await asyncio.gather(_do_direct(), _do_search())

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

        # --- Step 4: Query type (for boosting) ---
        query_type = self._classify_query(query_text)
        logger.info("Query type: %s", query_type)
        boost_multiplier = (
            2.5 if query_type == "statute_interpretation" else (2.0 if query_type == "conditions" else 1.5)
        )
        # --- Step 5: Rerank with Cohere (or skip for fast mode) ---
        top_k = final_limit if final_limit is not None else config.CHUNKS_TO_LLM
        if config.RERANK_ENABLED:
            logger.info("Reranking...")
            rerank_start = time.time()
            reranker = self._get_reranker()
            rerank_n = min(config.RERANK_MAX_DOCS, len(combined))
            reranked = reranker.rerank(query_text, combined[:rerank_n], top_k=rerank_n)
            logger.info("Rerank done → top %s in %.1fs", len(reranked), time.time() - rerank_start)
            reranked = self._rrf_blend_scores(reranked, k=60)
        else:
            # Fast mode: use pre-rerank order (RRF from hybrid), apply exact-match boost only
            reranked = combined[: min(config.RERANK_MAX_DOCS, len(combined))]
            for r in reranked:
                base = r.get("score", 0) or 0.3  # 0.3 for direct chunks (no score)
                r["rerank_score"] = base
                r["blended_score"] = base

        # --- Step 7: Exact-match boost (statute/case ID in chunk) ---
        for r in reranked:
            exact_boost = self._compute_exact_match_boost(r, query_text)
            r["blended_score"] = r.get("blended_score", 0) * (exact_boost ** (boost_multiplier - 1))
        reranked.sort(key=lambda x: x.get("blended_score", 0), reverse=True)

        # --- Step 8: Smart diversity cap (top 2 uncapped, then max 3 per case) ---
        reranked = self._smart_diversity_cap(reranked, max_per_case=3, top_k=top_k)

        # --- Step 9: When query mentions specific case(s), put those chunks first ---
        if mentioned_ids and reranked:
            mentioned_set = {c.upper() for c in mentioned_ids}
            from_asked = [r for r in reranked if (r.get("metadata") or {}).get("case_id", "").upper() in mentioned_set]
            others = [r for r in reranked if (r.get("metadata") or {}).get("case_id", "").upper() not in mentioned_set]
            reranked = from_asked + others
            if from_asked:
                logger.info("Focus case(s) %s → %s chunks prioritized", mentioned_ids, len(from_asked))

        # Optional: log rank of first mentioned case in final list (for debugging)
        if mentioned_ids and reranked:
            focus = mentioned_ids[0].upper()
            for i, r in enumerate(reranked):
                if ((r.get("metadata") or {}).get("case_id") or "").upper() == focus:
                    logger.info("Focus case %s final rank: %s", focus, i + 1)
                    break

        logger.info("Final results sent to LLM:")
        for i, r in enumerate(reranked):
            meta = r.get("metadata", {})
            label = meta.get("case_id") or meta.get("title") or meta.get("uri") or "?"
            logger.info("  [%s] %s | blended=%.4f", i + 1, label, r.get("blended_score", 0))

        return reranked
