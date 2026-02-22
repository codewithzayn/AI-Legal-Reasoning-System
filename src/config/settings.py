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
    SEARCH_CANDIDATES_FOR_RERANK: int = int(os.getenv("SEARCH_CANDIDATES_FOR_RERANK", "75"))
    CHUNKS_TO_LLM: int = int(os.getenv("CHUNKS_TO_LLM", "30"))
    # Max chunks per case after rerank. Lower = more unique cases for topic queries.
    MAX_CHUNKS_PER_CASE: int = int(os.getenv("MAX_CHUNKS_PER_CASE", "2"))
    # Max documents sent to Cohere reranker. Higher = better recall, slower.
    # 50 ensures deeper candidates still get a fair reranking.
    RERANK_MAX_DOCS: int = int(os.getenv("RERANK_MAX_DOCS", "50"))
    # Set to false to skip Cohere rerank (use hybrid + RRF + exact-match only). Saves ~15-25s.
    RERANK_ENABLED: bool = (os.getenv("RERANK_ENABLED", "true")).strip().lower() in ("true", "1", "yes")
    # Set to false to skip relevancy check (saves ~2-5s, no score shown).
    RELEVANCY_CHECK_ENABLED: bool = (os.getenv("RELEVANCY_CHECK_ENABLED", "true")).strip().lower() in (
        "true",
        "1",
        "yes",
    )

    # Multi-query expansion: generate alternative queries via LLM to improve recall.
    # Set to "false" to disable (saves 1 LLM call + 2 hybrid searches; uses single hybrid search).
    MULTI_QUERY_ENABLED: bool = (os.getenv("MULTI_QUERY_ENABLED", "true")).strip().lower() in ("true", "1", "yes")
    # When true: skip multi-query expansion when user explicitly mentions a case ID (e.g. KKO:2024:76).
    # Saves 2 LLM calls + 2 hybrid searches; direct lookup + single search suffice.
    MULTI_QUERY_SKIP_WHEN_CASE_ID: bool = (os.getenv("MULTI_QUERY_SKIP_WHEN_CASE_ID", "true")).strip().lower() in (
        "true",
        "1",
        "yes",
    )

    # Reformulate: when search returns 0 results, rewrite query and retry (up to 2 attempts).
    # Set to "false" to skip reformulation and go straight to "I couldn't find" apology.
    REFORMULATE_ENABLED: bool = (os.getenv("REFORMULATE_ENABLED", "true")).strip().lower() in ("true", "1", "yes")

    # When true: ask for year range when user's legal query has no case ID and no year specified.
    # Set to "false" to skip and search all years.
    YEAR_CLARIFICATION_ENABLED: bool = (os.getenv("YEAR_CLARIFICATION_ENABLED", "true")).strip().lower() in (
        "true",
        "1",
        "yes",
    )

    # Query-time answer generator (user asks a question). Default: cheaper/fast.
    OPENAI_CHAT_MODEL: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    # Lightweight model for support tasks (intent, expansion, relevancy, suggestions).
    OPENAI_SUPPORT_MODEL: str = os.getenv("OPENAI_SUPPORT_MODEL", "gpt-4o-mini")
    # Max tokens for LLM response. Higher = comprehensive legal analysis memos with multiple cases.
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "4000"))
    # Timeout for LLM requests (seconds).
    LLM_REQUEST_TIMEOUT: int = int(os.getenv("LLM_REQUEST_TIMEOUT", "90"))

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

    # Document Upload Limits (client document ingestion)
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
    MAX_UPLOAD_SIZE_BYTES: int = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    # Timeout for document ingestion per file (seconds). Extraction + embedding can be slow for large docs.
    INGESTION_TIMEOUT_SECONDS: int = int(os.getenv("INGESTION_TIMEOUT_SECONDS", "300"))

    # EU Case Law (EUR-Lex CELLAR, CURIA, HUDOC)
    EU_CASE_LAW_ENABLED: bool = (os.getenv("EU_CASE_LAW_ENABLED", "false")).strip().lower() in ("true", "1", "yes")
    EURLEX_SPARQL_ENDPOINT: str = os.getenv(
        "EURLEX_SPARQL_ENDPOINT", "https://publications.europa.eu/webapi/rdf/sparql"
    )
    EURLEX_REST_ENDPOINT: str = os.getenv("EURLEX_REST_ENDPOINT", "https://eur-lex.europa.eu/eurlex-ws/rest")
    CURIA_BASE_URL: str = os.getenv("CURIA_BASE_URL", "https://curia.europa.eu")
    HUDOC_API_URL: str = os.getenv("HUDOC_API_URL", "https://hudoc.echr.coe.int/app/query/results")

    # Session lifetime (seconds). Default: 1 hour. Controls cookie max-age and idle timer.
    SESSION_LIFETIME_SECONDS: int = int(os.getenv("SESSION_LIFETIME_SECONDS", "3600"))

    # Application base URL (for OAuth redirect callbacks).
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://localhost:8501").strip().rstrip("/")

    # Multi-tenant client document ingestion (legacy; overridden by auth user_id when logged in).
    LEXAI_TENANT_ID: str = os.getenv("LEXAI_TENANT_ID", "").strip()

    # Google Drive OAuth for client ingestion (web flow)
    GOOGLE_DRIVE_CLIENT_ID: str = os.getenv("GOOGLE_DRIVE_CLIENT_ID", "").strip()
    GOOGLE_DRIVE_CLIENT_SECRET: str = os.getenv("GOOGLE_DRIVE_CLIENT_SECRET", "").strip()

    # Microsoft OneDrive OAuth for client ingestion
    MICROSOFT_CLIENT_ID: str = os.getenv("MICROSOFT_CLIENT_ID", "").strip()
    MICROSOFT_CLIENT_SECRET: str = os.getenv("MICROSOFT_CLIENT_SECRET", "").strip()


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


def _validate_api_keys() -> list[str]:
    """Check conditional API key requirements."""
    errors: list[str] = []
    if config.USE_AI_EXTRACTION and not os.getenv("OPENAI_API_KEY", "").strip():
        errors.append("USE_AI_EXTRACTION=true requires OPENAI_API_KEY to be set.")
    if config.RERANK_ENABLED and not os.getenv("COHERE_API_KEY", "").strip():
        errors.append("RERANK_ENABLED=true requires COHERE_API_KEY to be set.")
    if config.EU_CASE_LAW_ENABLED and not config.EURLEX_SPARQL_ENDPOINT:
        errors.append("EU_CASE_LAW_ENABLED=true requires EURLEX_SPARQL_ENDPOINT to be set.")
    return errors


def _validate_numeric_ranges() -> list[str]:
    """Check that numeric config values are within valid ranges."""
    errors: list[str] = []
    if not (0.0 < config.MATCH_THRESHOLD < 1.0):
        errors.append(f"MATCH_THRESHOLD={config.MATCH_THRESHOLD} is out of range (0, 1).")
    positive_fields = {
        "CHUNK_SIZE": config.CHUNK_SIZE,
        "CHUNK_MIN_SIZE": config.CHUNK_MIN_SIZE,
        "VECTOR_SEARCH_TOP_K": config.VECTOR_SEARCH_TOP_K,
        "FTS_SEARCH_TOP_K": config.FTS_SEARCH_TOP_K,
        "RERANK_TOP_K": config.RERANK_TOP_K,
        "CHUNKS_TO_LLM": config.CHUNKS_TO_LLM,
        "LLM_MAX_TOKENS": config.LLM_MAX_TOKENS,
        "LLM_REQUEST_TIMEOUT": config.LLM_REQUEST_TIMEOUT,
        "EMBEDDING_DIMENSIONS": config.EMBEDDING_DIMENSIONS,
        "MAX_QUERY_LENGTH": config.MAX_QUERY_LENGTH,
        "MAX_UPLOAD_SIZE_MB": config.MAX_UPLOAD_SIZE_MB,
        "INGESTION_TIMEOUT_SECONDS": config.INGESTION_TIMEOUT_SECONDS,
    }
    for name, value in positive_fields.items():
        if value <= 0:
            errors.append(f"{name}={value} must be > 0.")
    if config.CHUNK_OVERLAP < 0:
        errors.append(f"CHUNK_OVERLAP={config.CHUNK_OVERLAP} must be >= 0.")
    if config.CHUNK_MIN_SIZE >= config.CHUNK_SIZE:
        errors.append(f"CHUNK_MIN_SIZE={config.CHUNK_MIN_SIZE} must be < CHUNK_SIZE={config.CHUNK_SIZE}.")
    return errors


def _validate_cross_field() -> list[str]:
    """Check cross-field constraints (model names, rerank/chunk limits)."""
    errors: list[str] = []
    for field, value in [
        ("OPENAI_CHAT_MODEL", config.OPENAI_CHAT_MODEL),
        ("OPENAI_SUPPORT_MODEL", config.OPENAI_SUPPORT_MODEL),
        ("EXTRACTION_MODEL", config.EXTRACTION_MODEL),
        ("EMBEDDING_MODEL", config.EMBEDDING_MODEL),
    ]:
        if not value or not value.strip():
            errors.append(f"{field} must not be empty.")
    if config.RERANK_MAX_DOCS < config.RERANK_TOP_K:
        errors.append(f"RERANK_MAX_DOCS={config.RERANK_MAX_DOCS} must be >= RERANK_TOP_K={config.RERANK_TOP_K}.")
    effective_candidates = (
        config.RERANK_TOP_K if config.RERANK_ENABLED else (config.VECTOR_SEARCH_TOP_K + config.FTS_SEARCH_TOP_K)
    )
    if effective_candidates < config.CHUNKS_TO_LLM:
        errors.append(f"CHUNKS_TO_LLM={config.CHUNKS_TO_LLM} exceeds effective candidates ({effective_candidates}).")
    return errors


def validate_config_dependencies() -> list[str]:
    """
    Validate cross-field config constraints and numeric ranges.
    Returns a list of human-readable error strings (empty = all OK).
    """
    return _validate_api_keys() + _validate_numeric_ranges() + _validate_cross_field()


# ============================================
# UI Configuration (static values)
# ============================================

APP_TITLE = "LexAI — Legal Analyst Copilot"
APP_ICON = "⚖️"
CHAT_WELCOME_MESSAGE = "Tervetuloa! Valmistan juristeille käyttövalmista tapausaineistoa."

# Streamlit Page Config
PAGE_CONFIG = {
    "page_title": APP_TITLE,
    "page_icon": APP_ICON,
    "layout": "wide",
    "initial_sidebar_state": "expanded",
}

# Chat Configuration
MAX_CHAT_HISTORY = int(os.getenv("MAX_CHAT_HISTORY", "50"))
USER_AVATAR = "👤"
ASSISTANT_AVATAR = "⚖️"
