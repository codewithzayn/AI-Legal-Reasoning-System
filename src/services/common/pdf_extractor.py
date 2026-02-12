"""
PDF Text Extractor Service
Downloads and extracts text from PDF documents
"""

import tempfile
from pathlib import Path
from typing import Any

import requests
from PyPDF2 import PdfReader

from src.config.logging_config import setup_logger

logger = setup_logger(__name__)


class PDFExtractor:
    """Extract text from PDF documents"""

    def __init__(self) -> None:
        self.timeout = 30  # seconds

    def extract_from_url(self, pdf_url: str) -> dict[str, Any]:
        """
        Download PDF from URL, extract text, and delete the file

        Args:
            pdf_url: URL to the PDF document

        Returns:
            Dict with 'text' and 'page_count'
        """
        temp_pdf_path = None

        try:
            # Step 1: Download PDF to temp file
            response = requests.get(pdf_url, timeout=self.timeout, stream=True)
            response.raise_for_status()

            # Create temp file
            with tempfile.NamedTemporaryFile(mode="wb", suffix=".pdf", delete=False) as temp_pdf:
                temp_pdf_path = temp_pdf.name
                # Write PDF content
                for chunk in response.iter_content(chunk_size=8192):
                    temp_pdf.write(chunk)

            logger.debug("PDF downloaded to %s", temp_pdf_path)

            # Step 2: Extract text from PDF
            logger.debug("Extracting text from PDF...")
            reader = PdfReader(temp_pdf_path)
            page_count = len(reader.pages)

            # Extract text from all pages
            text_parts = []
            for _page_num, page in enumerate(reader.pages, 1):
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)

            full_text = "\n\n".join(text_parts)

            logger.info("Extracted %s characters from %s pages", len(full_text), page_count)

            return {"text": full_text, "page_count": page_count, "char_count": len(full_text)}

        except requests.RequestException as e:
            raise Exception(f"Failed to download PDF: {e!s}") from e
        except Exception as e:
            raise Exception(f"Failed to extract text from PDF: {e!s}") from e
        finally:
            # Step 3: Delete temp PDF file
            if temp_pdf_path and Path(temp_pdf_path).exists():
                try:
                    Path(temp_pdf_path).unlink()
                    logger.debug("Deleted temp PDF: %s", temp_pdf_path)
                except Exception as e:
                    logger.warning("Failed to delete temp PDF %s: %s", temp_pdf_path, e)
