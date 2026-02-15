"""
Hybrid Retrieval Service
Combines vector search, full-text search, RRF ranking,
multi-query expansion, and direct case-ID lookup.
"""

import asyncio
import os
import re
import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from postgrest.exceptions import APIError as PostgrestAPIError
from supabase import AsyncClient, create_async_client

from src.config.logging_config import setup_logger
from src.config.settings import config  # load_dotenv() runs here
from src.services.common.embedder import DocumentEmbedder
from src.services.protocols import EmbeddingService
from src.utils.retry import retry_async

from .reranker import CohereReranker

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# Finnish stop words — stripped from FTS queries so only substantive
# legal terms remain.  When combined with to_tsquery OR (|) mode
# this gives broad recall while ts_rank scores precision.
# ---------------------------------------------------------------------------
_FINNISH_FTS_STOPWORDS: frozenset[str] = frozenset(
    {
        # Question / modal words
        "onko",
        "voiko",
        "oliko",
        "miksi",
        "miten",
        "milloin",
        "missä",
        "mitä",
        "kuka",
        "minne",
        "mistä",
        "mikä",
        "kumpi",
        "voidaan",
        "pitää",
        "täytyy",
        "saako",
        "tuleeko",
        # Conjunctions & particles
        "ja",
        "tai",
        "vai",
        "sekä",
        "että",
        "mutta",
        "kun",
        "jos",
        "eli",
        "niin",
        "myös",
        "joka",
        "kuin",
        "koska",
        "vaikka",
        "siis",
        "kuitenkin",
        "eikä",
        "vain",
        # Prepositions & postpositions
        "mukaan",
        "kanssa",
        "ennen",
        "jälkeen",
        "yli",
        "alle",
        "vuoksi",
        "perusteella",
        "nojalla",
        "lisäksi",
        "välillä",
        # Pronouns & demonstratives
        "tämä",
        "tuo",
        "sen",
        "tämän",
        "nämä",
        "nuo",
        "sitä",
        "siitä",
        "hän",
        "hänen",
        "he",
        "heidän",
        "minä",
        "sinä",
        "me",
        "te",
        "näiden",
        "niiden",
        "muun",
        # Common verbs (base + inflections)
        "olla",
        "ole",
        "ollut",
        "oleva",
        "ollaan",
        "olisi",
        "ovat",
        # Legal structure words (chapter/section markers)
        "luvun",
        "pykälän",
        "kohdan",
        "momentin",
        # Misc
        "kyllä",
        "aina",
        "jo",
        # English filler words (users sometimes mix English in queries)
        "tell",
        "about",
        "what",
        "how",
        "does",
        "the",
        "this",
        "that",
        "which",
        "when",
        "where",
        "please",
    }
)

# ---------------------------------------------------------------------------
# Compound-word prefix matching.  The PostgreSQL Finnish stemmer cannot
# decompose compound words, so "oikeuspaikkasäännös" never matches
# "oikeuspaikka" in the tsvector.  Instead of hardcoding known suffixes
# (which only covers specific terms), we generate prefix-match variants
# for ANY long word using to_tsquery :* (prefix operator).  This is fully
# generic — works for any compound word in any question, without needing
# a dictionary or suffix list.
#
# _PREFIX_RATIOS: truncation points as a fraction of word length.
#   Multiple ratios increase the chance that at least one truncation
#   lands on a compound-word boundary.
# ---------------------------------------------------------------------------
_COMPOUND_PREFIX_MIN_LENGTH = 10
_PREFIX_RATIOS: tuple[float, ...] = (0.50, 0.65, 0.80)

# ---------------------------------------------------------------------------
# Regex to detect case IDs like KKO:2022:18, KHO:2023:5, KKO 2024:76, etc.
# Supports: KKO:2024:76, KKO 2024:76, KKO2025:58 (no space),
#           KKO 2025 58 (space-only), KKO/2024/76 (slash variant),
#           KKO:2024-II-76 (old format with Roman numeral volume)
# ---------------------------------------------------------------------------
_CASE_ID_RE = re.compile(
    r"\b(KKO|KHO)\s*[:\-/\s]\s*(\d{4})\s*[:\-/\s]\s*(?:(?:II|I)\s*[:\-/\s]\s*)?(\d+)\b",
    re.IGNORECASE,
)

_expansion_llm_holder: list = []  # lazy singleton; list avoids global statement


def _get_expansion_llm():
    if not _expansion_llm_holder:
        _expansion_llm_holder.append(ChatOpenAI(model="gpt-4o-mini", temperature=0.4))
    return _expansion_llm_holder[0]


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

    def __init__(
        self,
        url: str | None = None,
        key: str | None = None,
        embedder: EmbeddingService | None = None,
        reranker: CohereReranker | None = None,
    ):
        """Initialize Supabase client, embedder, and optional reranker.

        Args:
            url: Supabase project URL. Falls back to SUPABASE_URL env var.
            key: Supabase anon/service key. Falls back to SUPABASE_KEY env var.
            embedder: Embedding service for query vectors. Falls back to
                      the default DocumentEmbedder (OpenAI text-embedding-3-small).
            reranker: Cohere reranker instance. Created lazily on first use when
                      not provided.
        """
        self.url = url or os.getenv("SUPABASE_URL")
        self.key = key or os.getenv("SUPABASE_KEY")

        if not self.url or not self.key:
            raise ValueError("Supabase URL and KEY required")

        self.client: AsyncClient | None = None
        self._client_lock = asyncio.Lock()
        self.embedder: EmbeddingService = embedder or DocumentEmbedder()
        self.reranker: CohereReranker | None = reranker

    async def _get_client(self) -> AsyncClient:
        """Lazy load async client with auto-reconnect on stale connections.

        Supabase free-tier drops idle TCP connections aggressively.
        When a request hits a dead connection we get:
          ``unable to perform operation on <TCPTransport closed=True …>``
        This method detects that state and creates a fresh client.
        """
        async with self._client_lock:
            if self.client is None:
                self.client = await create_async_client(self.url, self.key)
        return self.client

    async def _reset_client(self) -> AsyncClient:
        """Force-recreate the Supabase client after a connection failure."""
        async with self._client_lock:
            logger.warning("Resetting Supabase client (stale connection)")
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
            response = await retry_async(
                lambda: _get_expansion_llm().ainvoke(
                    [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=f"Alkuperäinen: {query}"),
                    ]
                )
            )
            lines = [ln.strip().lstrip("0123456789.-) ") for ln in response.content.strip().splitlines() if ln.strip()]
            alternatives = [ln for ln in lines if ln][:2]
            if alternatives:
                logger.info("Multi-query expansion → %s alternatives", len(alternatives))
                for i, alt in enumerate(alternatives, 1):
                    logger.info("  alt-%s: %s", i, alt)
            return alternatives
        except (OSError, ValueError) as e:
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
        query_statutes = {s.upper() for s in re.findall(statute_pattern, query, re.IGNORECASE)}
        chunk_statutes = {s.upper() for s in re.findall(statute_pattern, text, re.IGNORECASE)}
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

        # Title keyword overlap: boost chunks whose case title shares
        # root words with the query.  Uses substring matching so that
        # compound words like "osamaksumyyjä" (query) match
        # "osamaksukauppa" (title) via the shared root "osamaksu".
        boost *= self._title_keyword_overlap_boost(chunk, query_lower, query_words)

        return boost

    @staticmethod
    def _title_keyword_overlap_boost(chunk: dict, query_lower: str, query_words: set[str]) -> float:
        """Compute a boost based on how well the case title matches the query.

        For each substantive query word (>=6 chars), checks whether
        a significant prefix (first 6+ chars) appears anywhere in the
        case title.  This catches Finnish compound-word overlaps:
        "osamaksumyyjä" and "osamaksukauppa" share the prefix "osamaksu".

        Returns:
            1.0 (no boost) when <2 roots match.
            1.3 when 2 roots match.
            1.6 when 3+ roots match.
        """
        case_title = ((chunk.get("metadata") or {}).get("case_title") or "").lower()
        if not case_title or not query_words:
            return 1.0

        title_root_matches = 0
        for word in query_words:
            if len(word) < 6:
                continue
            # Use the first 6 characters as a root prefix for compound matching
            root_prefix = word[:6]
            if root_prefix in case_title:
                title_root_matches += 1

        if title_root_matches >= 3:
            return 1.6
        if title_root_matches >= 2:
            return 1.3
        return 1.0

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
    def _smart_diversity_cap(
        results: list[dict],
        max_per_case: int = 3,
        top_k: int = 15,
        exempt_case_ids: set[str] | None = None,
    ) -> list[dict]:
        """Keep top 2 chunks uncapped, then apply per-case cap for the rest.

        Cases whose case_id is in *exempt_case_ids* (user explicitly mentioned
        them in the query) bypass the per-case cap so we never discard chunks
        the user specifically asked about.
        """
        exempt = {c.upper() for c in (exempt_case_ids or set())}
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
            is_exempt = cid.upper() in exempt
            if is_exempt or case_counts.get(cid, 0) < max_per_case:
                output.append(r)
                case_counts[cid] = case_counts.get(cid, 0) + 1
        return output

    # ------------------------------------------------------------------
    # Direct case-ID lookup
    # ------------------------------------------------------------------
    @staticmethod
    def extract_case_ids(query: str) -> list[str]:
        """Extract case IDs (e.g. KKO:2022:18, KKO:1983-II-124) mentioned in the query."""
        ids: list[str] = []
        # Modern format: KKO:2024:76 or KKO 2024:76
        for court, year, number in _CASE_ID_RE.findall(query):
            ids.append(f"{court.upper()}:{year}:{number}")
        # Old format: KKO:1983-II-124 (with Roman numeral volume)
        old_fmt = re.findall(r"\b(KKO|KHO)\s*[:\s]\s*(\d{4})\s*-\s*(I{1,2})\s*-\s*(\d+)\b", query, re.IGNORECASE)
        for court, year, vol, number in old_fmt:
            ids.append(f"{court.upper()}:{year}-{vol.upper()}-{number}")
        return list(dict.fromkeys(ids))  # deduplicate, preserve order

    async def fetch_case_chunks(self, case_id: str) -> list[dict]:
        """Fetch ALL chunks for a specific case_id directly from Supabase.
        This bypasses vector search entirely — guarantees we have the
        document's content when the user references it by ID."""
        try:
            client = await self._get_client()
            case_law_resp = await client.table("case_law").select("id").eq("case_id", case_id).limit(1).execute()
            if not case_law_resp.data or len(case_law_resp.data) == 0:
                logger.info("Direct case lookup → case %s not found in DB", case_id)
                return []

            case_law_id = case_law_resp.data[0]["id"]
            response = (
                await client.table("case_law_sections")
                .select("id, content, section_type, section_title, case_law_id")
                .eq("case_law_id", case_law_id)
                .execute()
            )

            # Also get case metadata for the normalized format
            case_meta = (
                await client.table("case_law")
                .select("case_id, court_type, case_year, legal_domains, title, decision_outcome, url")
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
                            "case_title": meta_row.get("title", ""),
                            "court": meta_row.get("court_type"),
                            "year": meta_row.get("case_year"),
                            "type": item.get("section_type"),
                            "keywords": meta_row.get("legal_domains", []),
                            "decision_outcome": meta_row.get("decision_outcome", ""),
                            "url": meta_row.get("url"),
                        },
                        "score": 1.0,  # max score for direct lookup
                    }
                )
            logger.info("Direct case lookup → %s chunks for %s", len(results), case_id)
            return results
        except (PostgrestAPIError, OSError) as e:
            logger.warning("Direct case lookup failed for %s: %s", case_id, e)
            return []

    # ------------------------------------------------------------------
    # Core search methods
    # ------------------------------------------------------------------
    async def vector_search(self, query_embedding: list[float], limit: int | None = None) -> list[dict]:
        """
        Vector similarity search on case_law_sections using HNSW index.

        Calls the ``vector_search_case_law`` RPC which leverages the HNSW
        index for fast approximate nearest-neighbour lookup.

        Args:
            query_embedding: Query embedding vector (1536-dim)
            limit: Number of results to return

        Returns:
            List of section dicts with similarity scores, normalised
            to the common format used by hybrid_search.
        """
        try:
            client = await self._get_client()
            response = await client.rpc(
                "vector_search_case_law",
                {
                    "query_embedding": query_embedding,
                    "match_threshold": config.MATCH_THRESHOLD,
                    "match_count": limit or config.VECTOR_SEARCH_TOP_K,
                },
            ).execute()

            # Normalise to the common format expected downstream
            results: list[dict] = []
            for item in response.data or []:
                results.append(
                    {
                        "id": item.get("section_id"),
                        "text": item.get("content", ""),
                        "source": "case_law",
                        "metadata": {
                            "case_id": item.get("case_id"),
                            "case_title": item.get("title", ""),
                            "court": item.get("court_type"),
                            "year": item.get("case_year"),
                            "type": item.get("section_type"),
                            "keywords": item.get("legal_domains", []),
                            "url": item.get("url"),
                        },
                        "score": item.get("similarity", 0),
                    }
                )
            return results
        except (PostgrestAPIError, OSError) as e:
            logger.error("Vector search error: %s", e)
            return []

    @staticmethod
    def _extract_key_terms(query: str, max_terms: int = 5) -> list[str]:
        """Extract substantive key terms from a Finnish legal query.

        Strips special characters, Finnish stop words, numbers, and
        short tokens.  Returns at most *max_terms* lower-cased terms,
        prioritising longer words (more likely to be distinctive legal
        terms) over short common words.

        Keeping the cap at 5 (down from 8) prevents ``websearch_to_tsquery``
        with many OR terms from timing out on the 67K-row GIN index.
        """
        sanitized = re.sub(r"[^\w\s]", " ", query)
        sanitized = re.sub(r"\s+", " ", sanitized).strip()

        key_terms: list[str] = []
        for word in sanitized.split():
            word_lower = word.lower()
            if word_lower in _FINNISH_FTS_STOPWORDS:
                continue
            if len(word) <= 2:
                continue
            if word.isdigit():
                continue
            key_terms.append(word_lower)

        # Sort by length descending so the most distinctive terms survive the cap
        key_terms.sort(key=len, reverse=True)
        return key_terms[:max_terms]

    @staticmethod
    def _build_fts_query(query: str) -> str:
        """Build an OR-based FTS query for ``websearch_to_tsquery``.

        Extracts key terms and joins them with ``OR`` so
        ``websearch_to_tsquery`` matches documents containing *any* of
        the terms (recall), while ``ts_rank`` scores higher when more
        terms match (precision).

        Returns an empty string when every word is a stop word so the
        caller can short-circuit (skip the RPC call).
        """
        key_terms = HybridRetrieval._extract_key_terms(query)
        if not key_terms:
            return ""
        return " OR ".join(key_terms)

    @staticmethod
    def _build_and_fts_query(query: str) -> str:
        """Build an AND-based FTS query for ``websearch_to_tsquery``.

        Takes the top 3 longest key terms (the most distinctive) and
        joins them with spaces.  ``websearch_to_tsquery`` treats
        space-separated tokens as implicit AND, so a match requires
        *all* terms to be present in the document.

        This produces fewer but more precisely relevant results than
        the OR-based query, functioning as a high-precision channel.

        Returns an empty string when fewer than 2 substantive terms
        remain (AND of a single term adds no value over OR).
        """
        key_terms = HybridRetrieval._extract_key_terms(query)
        if len(key_terms) < 2:
            return ""
        # Top 3 longest terms — already sorted by length descending
        and_terms = key_terms[:3]
        return " ".join(and_terms)

    @staticmethod
    def _build_prefix_tsquery(query: str) -> str:
        """Build a ``to_tsquery``-compatible query with ``:*`` prefix variants.

        Strategy
        --------
        Take the 2–3 longest key terms (most likely Finnish compounds) and
        build an **AND-of-OR-groups** query:

            (word1 | prefix1a:* | prefix1b:*) & (word2 | prefix2a:* | prefix2b:*)

        Each group contains the original word OR'd with its prefix variants
        (at 50 %, 65 %, 80 % of word length).  Groups are AND'd so a
        matching document must contain at least one form of EACH important
        term.  This is far more precise than a flat OR across all terms.

        Shorter words (≤ 10 chars, unlikely to be compounds) are appended
        as a flat OR suffix so they help ranking but don't exclude documents.

        Used for direct table queries via Supabase ``text_search`` which
        calls ``to_tsquery`` under the hood.
        """
        key_terms = HybridRetrieval._extract_key_terms(query)
        if not key_terms:
            return ""

        # Split terms into "long" (likely compounds) and "short" (not compounds).
        long_terms: list[str] = sorted(
            (t for t in key_terms if len(t) > _COMPOUND_PREFIX_MIN_LENGTH),
            key=len,
            reverse=True,
        )
        short_terms: list[str] = [t for t in key_terms if len(t) <= _COMPOUND_PREFIX_MIN_LENGTH]

        # Only AND the top 2 longest compound terms (most distinctive).
        # Extra long terms and all short terms go into a flat OR suffix.
        and_candidates = long_terms[:2]
        or_extras = long_terms[2:] + short_terms

        # Build one OR group per AND candidate: original | prefix_50 | prefix_65 | prefix_80
        and_groups: list[str] = []
        for term in and_candidates:
            group_parts = [term]
            seen: set[str] = {term}
            for ratio in _PREFIX_RATIOS:
                prefix_len = max(6, int(len(term) * ratio))
                if prefix_len >= len(term) - 2:
                    continue
                prefix_with_star = f"{term[:prefix_len]}:*"
                if prefix_with_star not in seen:
                    group_parts.append(prefix_with_star)
                    seen.add(prefix_with_star)
            # Parenthesise the OR group if it has multiple parts
            if len(group_parts) > 1:
                and_groups.append(f"( {' | '.join(group_parts)} )")
            else:
                and_groups.append(group_parts[0])

        if not and_groups:
            # No compound words — fall back to flat OR of all terms
            all_remaining = or_extras if or_extras else key_terms
            return " | ".join(all_remaining) if all_remaining else ""

        # AND the compound-term groups together (high precision)
        core = " & ".join(and_groups)

        # Append remaining terms as a flat OR suffix (helps ranking but
        # doesn't exclude documents that lack them).
        if or_extras:
            extras_or = " | ".join(or_extras)
            return f"{core} | {extras_or}"

        return core

    async def fts_search(self, query_text: str, limit: int | None = None) -> list[dict]:
        """
        Full-text search on case_law_sections using GIN index.

        Calls the ``fts_search_case_law`` RPC which leverages the GIN
        index on ``fts_vector`` for fast Finnish-stemmed keyword search.

        The query is pre-processed by ``_build_fts_query`` which extracts
        key terms and joins them with OR so ``websearch_to_tsquery`` can
        match documents containing *any* of the terms (recall), while
        ``ts_rank`` naturally scores higher when more terms match
        (precision).

        Args:
            query_text: Search query in Finnish
            limit: Number of results to return

        Returns:
            List of section dicts with relevance scores, normalised
            to the common format used by hybrid_search.
        """
        try:
            fts_query = self._build_fts_query(query_text)
            if not fts_query.strip():
                return []

            client = await self._get_client()
            response = await client.rpc(
                "fts_search_case_law",
                {
                    "query_text": fts_query,
                    "match_count": limit or config.FTS_SEARCH_TOP_K,
                },
            ).execute()

            # Normalise to the common format expected downstream
            results: list[dict] = []
            for item in response.data or []:
                results.append(
                    {
                        "id": item.get("section_id"),
                        "text": item.get("content", ""),
                        "source": "case_law",
                        "metadata": {
                            "case_id": item.get("case_id"),
                            "case_title": item.get("title", ""),
                            "court": item.get("court_type"),
                            "year": item.get("case_year"),
                            "type": item.get("section_type"),
                            "keywords": item.get("legal_domains", []),
                            "url": item.get("url"),
                        },
                        "score": item.get("rank", 0),
                    }
                )
            return results
        except (PostgrestAPIError, OSError) as e:
            logger.error("FTS search error: %s", e)
            return []

    async def and_fts_search(self, query_text: str, limit: int | None = None) -> list[dict]:
        """AND-based FTS on case_law_sections — high-precision channel.

        Requires the top 3 key terms to ALL appear in the same section.
        Produces fewer results than the OR channel but each result is
        far more likely to be topically relevant.  Merging this channel
        into RRF alongside the OR channel gives documents that match
        ALL terms a double RRF contribution, boosting them above
        generic single-term matches.
        """
        try:
            and_query = self._build_and_fts_query(query_text)
            if not and_query.strip():
                return []

            client = await self._get_client()
            response = await client.rpc(
                "fts_search_case_law",
                {
                    "query_text": and_query,
                    "match_count": limit or config.FTS_SEARCH_TOP_K,
                },
            ).execute()

            results: list[dict] = []
            for item in response.data or []:
                results.append(
                    {
                        "id": item.get("section_id"),
                        "text": item.get("content", ""),
                        "source": "case_law",
                        "metadata": {
                            "case_id": item.get("case_id"),
                            "case_title": item.get("title", ""),
                            "court": item.get("court_type"),
                            "year": item.get("case_year"),
                            "type": item.get("section_type"),
                            "keywords": item.get("legal_domains", []),
                            "url": item.get("url"),
                        },
                        "score": item.get("rank", 0),
                    }
                )
            if results:
                logger.info("AND-FTS → %s section(s)", len(results))
            return results
        except (PostgrestAPIError, OSError) as e:
            logger.warning("AND-FTS search error (non-critical): %s", e)
            return []

    def rrf_merge(self, *result_lists: list[dict], k: int = 60) -> list[dict]:
        """
        Reciprocal Rank Fusion (RRF) to merge multiple ranked result lists.

        Formula: RRF_score = Σ 1/(k + rank_i) for each list where the
        chunk appears.  A chunk found in multiple lists gets a higher score,
        naturally rewarding agreement across search channels.

        Args:
            *result_lists: One or more ranked result lists (vector, FTS, metadata, etc.)
            k: Smoothing constant (default: 60)

        Returns:
            Merged and re-ranked results sorted by RRF score descending.
        """
        # Build per-list rank maps
        rank_maps: list[dict[str, int]] = []
        for results in result_lists:
            rank_maps.append({item["id"]: rank + 1 for rank, item in enumerate(results)})

        # Collect all unique chunk IDs across every list
        all_ids: set[str] = set()
        for rank_map in rank_maps:
            all_ids |= set(rank_map.keys())

        # Calculate RRF scores
        rrf_scores: dict[str, float] = {}
        for chunk_id in all_ids:
            score = 0.0
            for rank_map in rank_maps:
                rank = rank_map.get(chunk_id, 0)
                if rank > 0:
                    score += 1.0 / (k + rank)
            rrf_scores[chunk_id] = score

        # Build a chunk-data lookup (first occurrence wins)
        chunks_map: dict[str, dict] = {}
        for results in result_lists:
            for item in results:
                if item["id"] not in chunks_map:
                    chunks_map[item["id"]] = item

        # Create merged results with RRF scores
        merged: list[dict] = []
        for chunk_id, rrf_score in rrf_scores.items():
            chunk = chunks_map[chunk_id].copy()
            chunk["rrf_score"] = rrf_score
            merged.append(chunk)

        # Sort by RRF score (descending)
        merged.sort(key=lambda x: x["rrf_score"], reverse=True)

        return merged

    async def search_case_law(
        self, query_embedding: list[float], query_text: str, limit: int | None = None
    ) -> list[dict]:
        """
        Search case law using the specific SQL function (Hybrid internally)
        """
        try:
            # Build FTS query for the internal function
            sanitized_query = self._build_fts_query(query_text)

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
                            "case_title": item.get("title", ""),
                            "court": item.get("court_type") or item.get("court"),
                            "year": item.get("case_year") or item.get("year"),
                            "type": item.get("section_type"),
                            "keywords": item.get("legal_domains", []),
                            "decision_outcome": item.get("decision_outcome", ""),
                            "url": item.get("url"),
                        },
                        "score": item.get("combined_score", 0),
                    }
                )
            return results
        except (PostgrestAPIError, OSError) as e:
            logger.error("Case law search error: %s", e)
            return []

    async def search_case_law_metadata(self, query_text: str, limit: int = 10) -> list[dict]:
        """Search case_law metadata columns (title, judgment, background_summary,
        decision_outcome, legal_domains, cited_cases, cited_laws, etc.) via FTS.

        Returns sections from cases whose *metadata* matches the query keywords.
        This closes the gap where a keyword lives in metadata but NOT in section embeddings.

        The RPC uses DISTINCT ON (case_id) wrapped in a subquery to return
        one row per case sorted by meta_score DESC.  No Python-side dedup
        is needed; match_count maps directly to the number of unique cases.
        """
        try:
            fts_query = self._build_fts_query(query_text)
            if not fts_query.strip():
                return []

            client = await self._get_client()
            response = await client.rpc(
                "search_case_law_metadata",
                {
                    "query_text": fts_query,
                    "match_count": limit,
                },
            ).execute()

            results: list[dict] = []
            for item in response.data or []:
                cid = item.get("case_id", "")
                results.append(
                    {
                        "id": item.get("section_id"),
                        "text": item.get("content", ""),
                        "source": "case_law",
                        "metadata": {
                            "case_id": cid,
                            "case_title": item.get("title", ""),
                            "court": item.get("court_type") or item.get("court"),
                            "year": item.get("case_year") or item.get("year"),
                            "type": item.get("section_type"),
                            "keywords": item.get("legal_domains", []),
                            "decision_outcome": item.get("decision_outcome", ""),
                            "url": item.get("url"),
                        },
                        "score": item.get("meta_score", 0),
                    }
                )
            # Sort by score descending (RPC returns DISTINCT ON case_id order)
            results.sort(key=lambda r: r["score"], reverse=True)
            if results:
                logger.info("Metadata FTS → %s unique case(s)", len(results))
            return results
        except (PostgrestAPIError, OSError) as e:
            logger.warning("Metadata FTS search failed (non-critical): %s", e)
            return []

    async def _case_id_fallback_search(self, case_id_pattern: str, limit: int = 5) -> list[dict]:
        """Fallback: find cases whose case_id matches a pattern via ILIKE.

        This ensures a directly requested case always appears even when FTS
        scoring misses it (e.g. empty metadata columns).  Uses existing
        Supabase client — no DB migration required.
        """
        try:
            client = await self._get_client()
            # Find matching case_law rows
            case_resp = (
                await client.table("case_law")
                .select("id, case_id, court_type, case_year, title, legal_domains, decision_outcome, url")
                .ilike("case_id", f"%{case_id_pattern}%")
                .limit(limit)
                .execute()
            )
            if not case_resp.data:
                return []

            results: list[dict] = []
            for case_row in case_resp.data:
                # Fetch sections for each matched case
                sec_resp = (
                    await client.table("case_law_sections")
                    .select("id, content, section_type, section_title")
                    .eq("case_law_id", case_row["id"])
                    .limit(5)
                    .execute()
                )
                for sec in sec_resp.data or []:
                    results.append(
                        {
                            "id": sec["id"],
                            "text": sec.get("content", ""),
                            "source": "case_law",
                            "metadata": {
                                "case_id": case_row.get("case_id", ""),
                                "case_title": case_row.get("title", ""),
                                "court": case_row.get("court_type"),
                                "year": case_row.get("case_year"),
                                "type": sec.get("section_type"),
                                "keywords": case_row.get("legal_domains", []),
                                "decision_outcome": case_row.get("decision_outcome", ""),
                                "url": case_row.get("url"),
                            },
                            "score": 0.95,  # high score for direct pattern match
                        }
                    )
            if results:
                logger.info("Case-ID fallback → %s chunks for pattern '%s'", len(results), case_id_pattern)
            return results
        except (PostgrestAPIError, OSError) as e:
            logger.warning("Case-ID fallback search failed (non-critical): %s", e)
            return []

    async def _prefix_title_search(self, query_text: str, limit: int = 10) -> list[dict]:
        """Find cases whose *title* matches prefix-expanded compound words.

        Uses direct table queries with ``to_tsquery`` (via Supabase
        ``text_search``) which supports the ``:*`` prefix operator.
        This bridges Finnish compound-word boundaries **generically**:
        e.g. ``oikeuspaikka:*`` matches a title containing "Oikeuspaikka"
        even when the user wrote "oikeuspaikkasäännös".

        No SQL migration or RPC change is required — the Supabase
        ``text_search`` filter calls ``to_tsquery`` under the hood.
        """
        prefix_query = self._build_prefix_tsquery(query_text)
        if not prefix_query:
            return []

        try:
            client = await self._get_client()
            case_resp = await (
                client.table("case_law")
                .select("id, case_id, court_type, case_year, title, legal_domains, decision_outcome, url")
                .text_search("title", prefix_query, options={"config": "finnish"})
                .execute()
            )
            if not case_resp.data:
                return []

            # Deduplicate by case_id (first occurrence wins)
            seen_cases: set[str] = set()
            unique_cases: list[dict] = []
            for row in case_resp.data:
                cid = row.get("case_id", "")
                if cid in seen_cases:
                    continue
                seen_cases.add(cid)
                unique_cases.append(row)
                if len(unique_cases) >= limit:
                    break

            # Fetch one section per matched case to provide chunk text
            results: list[dict] = []
            section_tasks = []
            for case_row in unique_cases:
                section_tasks.append(
                    client.table("case_law_sections")
                    .select("id, content, section_type")
                    .eq("case_law_id", case_row["id"])
                    .limit(1)
                    .execute()
                )

            section_responses = await asyncio.gather(*section_tasks, return_exceptions=True)

            for case_row, sec_resp in zip(unique_cases, section_responses, strict=True):
                if isinstance(sec_resp, BaseException) or not sec_resp.data:
                    continue
                sec = sec_resp.data[0]
                results.append(
                    {
                        "id": sec["id"],
                        "text": sec.get("content", ""),
                        "source": "case_law",
                        "metadata": {
                            "case_id": case_row.get("case_id", ""),
                            "case_title": case_row.get("title", ""),
                            "court": case_row.get("court_type"),
                            "year": case_row.get("case_year"),
                            "type": sec.get("section_type"),
                            "keywords": case_row.get("legal_domains", []),
                            "decision_outcome": case_row.get("decision_outcome", ""),
                            "url": case_row.get("url"),
                        },
                        "score": 0.5,
                    }
                )
            if results:
                logger.info("Prefix title FTS → %s case(s)", len(results))
            return results
        except (PostgrestAPIError, OSError) as exc:
            logger.warning("Prefix title search failed (non-critical): %s", exc)
            return []

    async def _prefix_content_search(self, query_text: str, limit: int = 15) -> list[dict]:
        """Prefix FTS on **section content** — compound-word bridge.

        Similar to ``_prefix_title_search`` but searches the full
        ``case_law_sections.fts_vector`` (67K rows) instead of just
        titles (13K rows).  Uses the ``prefix_fts_search_case_law``
        RPC which calls ``to_tsquery`` (supports ``:*`` prefix).

        This fixes the core compound-word matching gap: a query about
        "osamaksumyyjä" now matches sections containing
        "osamaksukauppa" because ``osamaksu:*`` matches both.
        """
        prefix_query = self._build_prefix_tsquery(query_text)
        if not prefix_query:
            return []

        try:
            client = await self._get_client()
            response = await client.rpc(
                "prefix_fts_search_case_law",
                {
                    "query_text": prefix_query,
                    "match_count": limit,
                },
            ).execute()

            results: list[dict] = []
            for item in response.data or []:
                results.append(
                    {
                        "id": item.get("section_id"),
                        "text": item.get("content", ""),
                        "source": "case_law",
                        "metadata": {
                            "case_id": item.get("case_id"),
                            "case_title": item.get("title", ""),
                            "court": item.get("court_type"),
                            "year": item.get("case_year"),
                            "type": item.get("section_type"),
                            "keywords": item.get("legal_domains", []),
                            "url": item.get("url"),
                        },
                        "score": item.get("rank", 0),
                    }
                )
            if results:
                logger.info("Prefix content FTS → %s section(s)", len(results))
            return results
        except (PostgrestAPIError, OSError) as exc:
            logger.warning("Prefix content search failed (non-critical): %s", exc)
            return []

    async def hybrid_search(self, query_text: str, limit: int = 20) -> list[dict]:
        """
        Hybrid Search on case_law_sections: 7 channels merged via RRF.

        Channels
        --------
        1. Vector (HNSW)           — semantic similarity
        2. FTS OR (GIN)            — broad keyword recall
        3. FTS AND (GIN)           — high-precision keyword co-occurrence
        4. Metadata FTS            — title / judgment / background / domains
        5. Prefix title FTS        — compound-word bridge on case titles
        6. Prefix content FTS      — compound-word bridge on section content
        7. Case-ID fallback        — direct lookup when query mentions a case

        Architecture
        ------------
        1. Embedding generation + all text-based searches run concurrently.
        2. Once the embedding is ready, vector search starts (uses HNSW).
        3. Channels 1–6 are merged via RRF; channel 7 is appended after.

        Each sub-query is capped at 15 s so one slow RPC never blocks all.
        Connection errors trigger an automatic client reset and single retry.
        """
        t0 = time.time()

        # Helper: run a search task with a timeout + connection recovery.
        async def _timed(coro, label: str, timeout: float = 15.0):
            try:
                return await asyncio.wait_for(coro, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning("  %s timed out after %.0fs", label, timeout)
                return []
            except OSError as exc:
                if "closed" in str(exc).lower() or "transport" in str(exc).lower():
                    logger.warning("  %s hit stale connection, resetting client: %s", label, exc)
                    await self._reset_client()
                return []

        # Generate embedding in thread pool (non-blocking)
        async def _get_embedding():
            loop = asyncio.get_event_loop()
            emb = await loop.run_in_executor(None, self.embedder.embed_query, query_text)
            logger.info("  embed: %.1fs", time.time() - t0)
            return emb

        # Log the FTS queries that will be sent (useful for debugging relevance)
        fts_query_preview = self._build_fts_query(query_text)
        and_fts_query_preview = self._build_and_fts_query(query_text)
        prefix_query_preview = self._build_prefix_tsquery(query_text)
        logger.info("  fts_or_query: %s", fts_query_preview)
        logger.info("  fts_and_query: %s", and_fts_query_preview)
        logger.info("  prefix_query: %s", prefix_query_preview)

        # Phase 1: Start text-only searches + embedding generation concurrently.
        embedding_task = asyncio.create_task(_get_embedding())
        fts_task = asyncio.create_task(_timed(self.fts_search(query_text, limit=config.FTS_SEARCH_TOP_K), "fts_or"))
        and_fts_task = asyncio.create_task(
            _timed(self.and_fts_search(query_text, limit=config.FTS_SEARCH_TOP_K), "fts_and")
        )
        meta_task = asyncio.create_task(_timed(self.search_case_law_metadata(query_text, limit=limit), "meta_fts"))
        # Prefix title search: bridges Finnish compound-word boundaries
        # by matching title keywords via to_tsquery :* prefix operator.
        prefix_title_task = asyncio.create_task(
            _timed(self._prefix_title_search(query_text, limit=limit), "prefix_title")
        )
        # Prefix content search: extends compound-word matching to section text.
        prefix_content_task = asyncio.create_task(
            _timed(self._prefix_content_search(query_text, limit=limit), "prefix_content")
        )

        # Case-ID fallback: if query mentions a case ID, fetch directly.
        mentioned_ids = self.extract_case_ids(query_text)
        fallback_tasks = [
            asyncio.create_task(_timed(self._case_id_fallback_search(cid), f"fallback_{cid}")) for cid in mentioned_ids
        ]

        # Phase 2: Wait for embedding, then launch vector search (HNSW).
        query_embedding = await embedding_task
        vec_task = asyncio.create_task(
            _timed(self.vector_search(query_embedding, limit=config.VECTOR_SEARCH_TOP_K), "vec")
        )

        # Wait for all parallel searches
        (
            vec_results,
            fts_results,
            and_fts_results,
            meta_results,
            prefix_title_results,
            prefix_content_results,
        ) = await asyncio.gather(vec_task, fts_task, and_fts_task, meta_task, prefix_title_task, prefix_content_task)

        # Collect case-ID fallback results
        fallback_results: list[dict] = []
        if fallback_tasks:
            fallback_lists = await asyncio.gather(*fallback_tasks)
            for fl in fallback_lists:
                fallback_results.extend(fl)

        t_search = time.time()
        logger.info(
            "  search: %.1fs (vec=%s, fts_or=%s, fts_and=%s, meta=%s, prefix_title=%s, prefix_content=%s, fallback=%s)",
            t_search - t0,
            len(vec_results),
            len(fts_results),
            len(and_fts_results),
            len(meta_results),
            len(prefix_title_results),
            len(prefix_content_results),
            len(fallback_results),
        )

        # RRF merge of ALL search channels (7 channels).
        # A document found by multiple channels gets a higher score,
        # naturally promoting the most topically relevant cases.
        rrf_merged = self.rrf_merge(
            vec_results,
            fts_results,
            and_fts_results,
            meta_results,
            prefix_title_results,
            prefix_content_results,
            k=60,
        )

        # Deduplicate: RRF merged first, then case-ID fallback
        seen_ids: set[str] = set()
        combined_results: list[dict] = []

        for chunk in rrf_merged:
            cid = chunk["id"]
            if cid not in seen_ids:
                seen_ids.add(cid)
                combined_results.append(chunk)

        for chunk in fallback_results:
            cid = chunk["id"]
            if cid not in seen_ids:
                seen_ids.add(cid)
                combined_results.append(chunk)

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
        pipeline_start = time.time()
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

        # --- Step 8: Smart diversity cap (top 2 uncapped, then max 2 per case) ---
        # Exempt explicitly mentioned case IDs from the cap so they get full coverage.
        exempt_ids = set(mentioned_ids) if mentioned_ids else None
        reranked = self._smart_diversity_cap(reranked, max_per_case=2, top_k=top_k, exempt_case_ids=exempt_ids)

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

        pipeline_elapsed = time.time() - pipeline_start
        logger.info("Pipeline total: %.1fs → %s chunks to LLM:", pipeline_elapsed, len(reranked))
        for i, r in enumerate(reranked):
            meta = r.get("metadata", {})
            label = meta.get("case_id") or meta.get("title") or meta.get("uri") or "?"
            logger.info("  [%s] %s | blended=%.4f", i + 1, label, r.get("blended_score", 0))

        return reranked
