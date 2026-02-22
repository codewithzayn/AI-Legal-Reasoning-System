"""
Unified Document Extractor with Enhanced Quality Metrics
Dispatches to the correct extractor based on file extension.
Adds extraction_confidence, completeness_score, and structured metadata.
"""

from typing import Any

from src.config.logging_config import setup_logger

from .docx_extractor import DocxExtractor
from .pdf_extractor import PDFExtractor
from .text_extractor import TextExtractor

logger = setup_logger(__name__)

_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


class DocumentExtractor:
    """Selects the right extractor by file extension and extracts text from bytes.

    Enhances extraction with quality metrics and structured metadata extraction.
    """

    def __init__(self) -> None:
        self._pdf = PDFExtractor()
        self._docx = DocxExtractor()
        self._txt = TextExtractor()

    @staticmethod
    def supported_extensions() -> set[str]:
        return _SUPPORTED_EXTENSIONS

    def extract_from_bytes(self, file_bytes: bytes, filename: str) -> dict[str, Any]:
        """Extract text from file bytes based on extension with quality metrics.

        Args:
            file_bytes: Raw file content.
            filename: Original filename (used to determine type).

        Returns:
            Dict with:
            - text: Extracted text
            - format: File format (pdf, docx, txt)
            - extraction_confidence: 0.0-1.0 quality score
            - completeness_score: 0.0-1.0 data completeness
            - extraction_method: text_layer, ocr, direct, etc.
            - pages: Number of pages (if applicable)
            - has_ocr: Whether OCR was used
            - warnings: List of quality issues
            - structured_data: Extracted metadata (parties, dates, etc.)
            - is_client_document: True (always for client uploads)

        Raises:
            ValueError: If file type is unsupported.
        """
        ext = _get_extension(filename)

        result = {}
        try:
            if ext == ".pdf":
                result = self._pdf.extract_from_bytes(file_bytes, filename)
            elif ext == ".docx":
                result = self._docx.extract_from_bytes(file_bytes, filename)
            elif ext == ".txt":
                result = self._txt.extract_from_bytes(file_bytes, filename)
            else:
                raise ValueError(f"Unsupported file type '{ext}'. Supported: {_SUPPORTED_EXTENSIONS}")
        except Exception as e:
            logger.error("Extraction failed for %s: %s", filename, e)
            raise

        # PHASE 1 ENHANCEMENT: Add quality metrics if not present
        if "extraction_confidence" not in result:
            result["extraction_confidence"] = self._estimate_confidence(result, ext)

        if "completeness_score" not in result:
            result["completeness_score"] = self._estimate_completeness(result, ext)

        if "extraction_method" not in result:
            result["extraction_method"] = "direct"  # or "ocr" if OCR was used

        if "warnings" not in result:
            result["warnings"] = []

        if "structured_data" not in result:
            result["structured_data"] = self._extract_structured_metadata(result.get("text", ""), ext)

        # Mark as client document (always true for uploaded docs)
        result["is_client_document"] = True
        result["format"] = ext.lstrip(".")

        return result

    @staticmethod
    def _estimate_confidence(result: dict, ext: str) -> float:
        """Estimate extraction quality (0.0-1.0).

        Based on:
        - Presence of text
        - Format type (PDFs with text layer = high confidence)
        - Presence of OCR (lower confidence)
        """
        text = result.get("text", "").strip()

        if not text:
            return 0.0  # No text extracted

        has_ocr = result.get("has_ocr", False)
        is_scanned = result.get("is_scanned", False)

        base_confidence = {
            "pdf": 0.95,  # PDFs with text layer
            "docx": 0.98,  # DOCX highly reliable
            "txt": 1.0,  # TXT is direct
        }.get(ext.lstrip("."), 0.8)

        if has_ocr or is_scanned:
            base_confidence *= 0.85  # Reduce confidence for OCR

        # Adjust based on text length (very short = likely extraction issue)
        if len(text) < 50:
            base_confidence *= 0.7

        return min(base_confidence, 1.0)

    @staticmethod
    def _estimate_completeness(result: dict, ext: str) -> float:
        """Estimate data completeness (0.0-1.0).

        Based on:
        - Text length (longer = more complete)
        - Presence of expected sections (for DOCX)
        - Page count vs. extracted length ratio
        """
        text = result.get("text", "").strip()
        pages = result.get("pages", 1)

        if not text:
            return 0.0

        # Rough heuristic: ~300-400 chars per page is typical
        expected_length = pages * 350
        actual_length = len(text)

        completeness = min(actual_length / expected_length, 1.0) if expected_length > 0 else 0.5

        # Boost if structured data found
        structured = result.get("structured_data", {})
        if structured:
            completeness = min(completeness + 0.1, 1.0)

        return completeness

    @staticmethod
    def _extract_structured_metadata(text: str, ext: str) -> dict:
        """Extract structured metadata from document text.

        Looks for: parties, dates, amounts, key terms.
        """
        import re

        metadata = {
            "parties": [],
            "dates": [],
            "amounts": [],
            "key_terms": [],
        }

        # Extract dates (YYYY-MM-DD or DD.MM.YYYY format)
        date_patterns = [
            r"\d{4}-\d{2}-\d{2}",  # YYYY-MM-DD
            r"\d{1,2}\.\d{1,2}\.\d{4}",  # DD.MM.YYYY
        ]
        for pattern in date_patterns:
            dates = re.findall(pattern, text)
            metadata["dates"].extend(dates)

        # Extract amounts (€ symbol or decimal numbers)
        amount_pattern = r"€[\s]?[\d\s,.]+"
        amounts = re.findall(amount_pattern, text)
        metadata["amounts"].extend(amounts)

        # Extract capitalized phrases (likely parties, titles, terms)
        capitalized_pattern = r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b"
        caps = re.findall(capitalized_pattern, text)
        # Filter out common words
        common_words = {"The", "This", "That", "All", "Each", "And", "Or", "By", "From", "To"}
        key_terms = [c for c in set(caps) if c not in common_words and len(c) > 3][:10]
        metadata["key_terms"] = key_terms

        return metadata


def _get_extension(filename: str) -> str:
    """Extract lowercase file extension from filename."""
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()
