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
    VECTOR_SEARCH_TOP_K: int = int(os.getenv("VECTOR_SEARCH_TOP_K", "50"))
    FTS_SEARCH_TOP_K: int = int(os.getenv("FTS_SEARCH_TOP_K", "50"))
    RERANK_TOP_K: int = int(os.getenv("RERANK_TOP_K", "5"))
    
    # Embedding Settings
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    EMBEDDING_DIMENSIONS: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
    
    # PDF Processing
    PDF_MAX_WORKERS: int = int(os.getenv("PDF_MAX_WORKERS", "4"))


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
    "initial_sidebar_state": "collapsed"
}

# Chat Configuration
MAX_CHAT_HISTORY = 50
USER_AVATAR = "👤"
ASSISTANT_AVATAR = "⚖️"
SYSTEM_STATUS = "🤖 LangGraph Agent Active"
