"""
Configuration settings for AI Legal Reasoning System
"""

import os

from dotenv import load_dotenv

load_dotenv()


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
    # Lower = faster search. 30 is a good balance for production (was 50).
    VECTOR_SEARCH_TOP_K: int = int(os.getenv("VECTOR_SEARCH_TOP_K", "30"))
    FTS_SEARCH_TOP_K: int = int(os.getenv("FTS_SEARCH_TOP_K", "30"))
    RERANK_TOP_K: int = int(os.getenv("RERANK_TOP_K", "10"))
    # How many candidates to fetch before rerank; then how many to send to the LLM.
    # Lower candidates = faster (especially Cohere rerank). 30 is a good balance for production.
    SEARCH_CANDIDATES_FOR_RERANK: int = int(os.getenv("SEARCH_CANDIDATES_FOR_RERANK", "30"))
    CHUNKS_TO_LLM: int = int(os.getenv("CHUNKS_TO_LLM", "10"))
    # Max documents sent to Cohere (fewer = faster). Default 20 for production latency.
    RERANK_MAX_DOCS: int = int(os.getenv("RERANK_MAX_DOCS", "20"))
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

    # Query-time answer generator (user asks a question). Default: cheaper/fast.
    OPENAI_CHAT_MODEL: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

    # Ingestion pipeline (extraction/chunking). Default: GPT-4o for better extraction quality.
    EXTRACTION_MODEL: str = os.getenv("EXTRACTION_MODEL", "gpt-4o")
    # Set to false for regex-only extraction (no LLM calls during ingestion; saves cost).
    USE_AI_EXTRACTION: bool = (os.getenv("USE_AI_EXTRACTION", "true")).strip().lower() in ("true", "1", "yes")

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


# Singleton instance
config = Config()


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
    "initial_sidebar_state": "collapsed",
}

# Chat Configuration
MAX_CHAT_HISTORY = 50
USER_AVATAR = "👤"
ASSISTANT_AVATAR = "⚖️"
