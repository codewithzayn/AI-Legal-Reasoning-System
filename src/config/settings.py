"""
Configuration settings for AI Legal Reasoning System
"""

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Use find_dotenv() to locate .env regardless of the current working directory.
# Falls back to an explicit path relative to this file (project root) if not found.
_dotenv_path = find_dotenv(usecwd=True) or str(Path(__file__).resolve().parent.parent.parent / ".env")
load_dotenv(_dotenv_path)


# ============================================
# Environment-based Configuration
# ============================================


class Config:
    """
    Centralized configuration loaded from environment variables.
    Edit .env file to change these values.
    """

    # Chunker Settings
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1000"))
    CHUNK_MIN_SIZE: int = int(os.getenv("CHUNK_MIN_SIZE", "100"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))

    # Retrieval Settings
    MATCH_THRESHOLD: float = float(os.getenv("MATCH_THRESHOLD", "0.3"))
    # Higher = better recall but slower. 25 balances recall vs latency.
    VECTOR_SEARCH_TOP_K: int = int(os.getenv("VECTOR_SEARCH_TOP_K", "25"))
    FTS_SEARCH_TOP_K: int = int(os.getenv("FTS_SEARCH_TOP_K", "25"))
    RERANK_TOP_K: int = int(os.getenv("RERANK_TOP_K", "10"))
    # How many candidates to fetch before rerank; then how many to send to the LLM.
    SEARCH_CANDIDATES_FOR_RERANK: int = int(os.getenv("SEARCH_CANDIDATES_FOR_RERANK", "50"))
    CHUNKS_TO_LLM: int = int(os.getenv("CHUNKS_TO_LLM", "12"))
    # Max documents sent to Cohere reranker. Higher = better recall, slower.
    # 50 ensures deeper candidates still get a fair reranking.
    RERANK_MAX_DOCS: int = int(os.getenv("RERANK_MAX_DOCS", "50"))
    # Set to false to skip Cohere rerank (use hybrid + RRF + exact-match only). Saves ~15-25s.
    RERANK_ENABLED: bool = (os.getenv("RERANK_ENABLED", "true")).strip().lower() in ("true", "1", "yes")
    # Set to false to skip relevancy check (saves ~2-5s, no score shown).
    RELEVANCY_CHECK_ENABLED: bool = (os.getenv("RELEVANCY_CHECK_ENABLED", "false")).strip().lower() in (
        "true",
        "1",
        "yes",
    )

    # Multi-query expansion: generate alternative queries via LLM to improve recall.
    # Set to "false" to disable (saves 1 cheap LLM call per question).
    MULTI_QUERY_ENABLED: bool = (os.getenv("MULTI_QUERY_ENABLED", "true")).strip().lower() in ("true", "1", "yes")
    # When true: skip multi-query expansion when user explicitly mentions a case ID (e.g. KKO:2024:76).
    # Saves 2 LLM calls + 2 hybrid searches; direct lookup + single search suffice.
    MULTI_QUERY_SKIP_WHEN_CASE_ID: bool = (os.getenv("MULTI_QUERY_SKIP_WHEN_CASE_ID", "true")).strip().lower() in (
        "true",
        "1",
        "yes",
    )

    # When true: ask for year range when user's legal query has no case ID and no year specified.
    # Set to "false" to skip and search all years.
    YEAR_CLARIFICATION_ENABLED: bool = (os.getenv("YEAR_CLARIFICATION_ENABLED", "true")).strip().lower() in (
        "true",
        "1",
        "yes",
    )

    # Query-time answer generator (user asks a question). Default: cheaper/fast.
    OPENAI_CHAT_MODEL: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

    # Ingestion pipeline (extraction/chunking). Default: GPT-4o for better extraction quality.
    EXTRACTION_MODEL: str = os.getenv("EXTRACTION_MODEL", "gpt-4o")
    # Set to false for regex-only extraction (no LLM calls during ingestion; saves cost).
    USE_AI_EXTRACTION: bool = (os.getenv("USE_AI_EXTRACTION", "true")).strip().lower() in ("true", "1", "yes")
    # When true: skip documents whose content_hash matches Supabase (faster, idempotent).
    # When false: always re-run pipeline and re-store (no skip). Use for re-ingest tests (e.g. 2000→1926).
    INGESTION_SKIP_UNCHANGED: bool = (os.getenv("INGESTION_SKIP_UNCHANGED", "false")).strip().lower() in (
        "true",
        "1",
        "yes",
    )

    # Embedding Settings
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    EMBEDDING_DIMENSIONS: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))

    # PDF Processing
    PDF_MAX_WORKERS: int = int(os.getenv("PDF_MAX_WORKERS", "4"))

    # Case law PDF export and Google Drive backup (separate pipeline)
    # 1 = write local + Drive (dev), 0 = Drive only (prod). Missing/empty => 1.
    CASE_LAW_EXPORT_LOCAL: str = (os.getenv("CASE_LAW_EXPORT_LOCAL") or "1").strip().lower()
    CASE_LAW_EXPORT_ROOT: str = (os.getenv("CASE_LAW_EXPORT_ROOT") or "data/case_law_export").strip()
    GOOGLE_DRIVE_ROOT_FOLDER_ID: str = (os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID") or "").strip()

    # Query length limit (chars) - reject oversize queries to avoid abuse and cost
    MAX_QUERY_LENGTH: int = int(os.getenv("MAX_QUERY_LENGTH", "2000"))


# Singleton instance
config = Config()


def validate_env_for_app() -> None:
    """
    Validate required env vars for the chat app. Call at startup.
    Raises SystemExit with clear message if any required var is missing.
    """
    required = {
        "SUPABASE_URL": os.getenv("SUPABASE_URL", "").strip(),
        "SUPABASE_KEY": os.getenv("SUPABASE_KEY", "").strip(),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "").strip(),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        msg = f"Missing required env vars: {', '.join(missing)}. Set them in .env or environment."
        raise SystemExit(msg)

    if config.RERANK_ENABLED:
        cohere_key = os.getenv("COHERE_API_KEY", "").strip()
        if not cohere_key:
            raise SystemExit("RERANK_ENABLED=true but COHERE_API_KEY is missing. Set it or disable rerank.")


# ============================================
# UI Configuration (static values)
# ============================================

APP_TITLE = "AI Legal Reasoning System"
APP_ICON = "⚖️"
CHAT_WELCOME_MESSAGE = "Tervetuloa! Ask me about Finnish legal documents."

# Streamlit Page Config
PAGE_CONFIG = {
    "page_title": APP_TITLE,
    "page_icon": APP_ICON,
    "layout": "centered",
    "initial_sidebar_state": "expanded",
}

# Chat Configuration
MAX_CHAT_HISTORY = 50
USER_AVATAR = "👤"
ASSISTANT_AVATAR = "⚖️"
