"""
Plain Text Extractor Service
Decodes raw bytes as UTF-8 text.
"""

from typing import Any

from src.config.logging_config import setup_logger

logger = setup_logger(__name__)


class TextExtractor:
    """Extract text from plain text files."""

    def extract_from_bytes(self, file_bytes: bytes, filename: str = "") -> dict[str, Any]:
        """Decode bytes as UTF-8 text.

        Args:
            file_bytes: Raw file bytes.
            filename: Original filename (for logging).

        Returns:
            Dict with 'text' and 'char_count'.
        """
        try:
            text = file_bytes.decode("utf-8")
            logger.info("Extracted %s characters from %s", len(text), filename)
            return {"text": text, "char_count": len(text)}
        except UnicodeDecodeError:
            # Fall back to latin-1 which never fails
            text = file_bytes.decode("latin-1")
            logger.warning("UTF-8 decode failed for %s, fell back to latin-1", filename)
            return {"text": text, "char_count": len(text)}
