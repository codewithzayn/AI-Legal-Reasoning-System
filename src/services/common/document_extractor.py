"""
Unified Document Extractor
Dispatches to the correct extractor based on file extension.
"""

from typing import Any

from src.config.logging_config import setup_logger

from .docx_extractor import DocxExtractor
from .pdf_extractor import PDFExtractor
from .text_extractor import TextExtractor

logger = setup_logger(__name__)

_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


class DocumentExtractor:
    """Selects the right extractor by file extension and extracts text from bytes."""

    def __init__(self) -> None:
        self._pdf = PDFExtractor()
        self._docx = DocxExtractor()
        self._txt = TextExtractor()

    @staticmethod
    def supported_extensions() -> set[str]:
        return _SUPPORTED_EXTENSIONS

    def extract_from_bytes(self, file_bytes: bytes, filename: str) -> dict[str, Any]:
        """Extract text from file bytes based on extension.

        Args:
            file_bytes: Raw file content.
            filename: Original filename (used to determine type).

        Returns:
            Dict with at least 'text' key.

        Raises:
            ValueError: If file type is unsupported.
        """
        ext = _get_extension(filename)
        if ext == ".pdf":
            return self._pdf.extract_from_bytes(file_bytes, filename)
        if ext == ".docx":
            return self._docx.extract_from_bytes(file_bytes, filename)
        if ext == ".txt":
            return self._txt.extract_from_bytes(file_bytes, filename)
        raise ValueError(f"Unsupported file type '{ext}'. Supported: {_SUPPORTED_EXTENSIONS}")


def _get_extension(filename: str) -> str:
    """Extract lowercase file extension from filename."""
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()
