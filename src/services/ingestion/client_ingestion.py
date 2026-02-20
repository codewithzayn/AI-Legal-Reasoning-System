"""
Client Document Ingestion Service
Orchestrates: download/upload → extract → chunk → embed → store with tenant_id.
"""

import hashlib
import uuid

from src.config.logging_config import setup_logger
from src.config.settings import config
from src.services.common.chunker import LegalDocumentChunker
from src.services.common.document_extractor import DocumentExtractor
from src.services.common.embedder import DocumentEmbedder

from .client_storage import ClientDocumentStorage

logger = setup_logger(__name__)


class ClientIngestionService:
    """Ingests client documents: extract text, chunk, embed, and store with tenant_id."""

    def __init__(self) -> None:
        self._extractor = DocumentExtractor()
        self._chunker = LegalDocumentChunker(
            max_chunk_size=config.CHUNK_SIZE,
            min_chunk_size=config.CHUNK_MIN_SIZE,
            overlap=config.CHUNK_OVERLAP,
        )
        self._embedder = DocumentEmbedder()
        self._storage = ClientDocumentStorage()

    def ingest_bytes(
        self,
        tenant_id: str,
        file_bytes: bytes,
        filename: str,
        source_provider: str = "upload",
        source_file_id: str | None = None,
        on_progress: callable = None,
    ) -> dict:
        """Ingest a document from raw bytes.

        Args:
            tenant_id: Tenant identifier.
            file_bytes: Raw file content.
            filename: Original filename.
            source_provider: 'upload', 'google_drive', or 'onedrive'.
            source_file_id: External file ID (from drive). Auto-generated if None.
            on_progress: Optional callback(stage: str, pct: float) for UI progress.

        Returns:
            Dict with 'case_law_id', 'chunks_count', 'status'.
        """
        file_id = source_file_id or str(uuid.uuid4())

        def _progress(stage: str, pct: float) -> None:
            if on_progress:
                on_progress(stage, pct)

        # Step 1: Check idempotency via content hash
        _progress("hashing", 0.05)
        content_hash = hashlib.sha256(file_bytes).hexdigest()
        if self._storage.document_exists(tenant_id, content_hash):
            logger.info("Document already ingested (hash match): %s", filename)
            return {"case_law_id": None, "chunks_count": 0, "status": "already_exists"}

        # Step 2: Extract text
        _progress("extracting", 0.15)
        logger.info("Extracting text from %s (%s bytes)...", filename, len(file_bytes))
        result = self._extractor.extract_from_bytes(file_bytes, filename)
        text = result.get("text", "")
        if not text.strip():
            logger.warning("No text extracted from %s", filename)
            return {"case_law_id": None, "chunks_count": 0, "status": "empty_document"}

        # Step 3: Chunk
        _progress("chunking", 0.35)
        logger.info("Chunking %s characters...", len(text))
        chunks = self._chunker.chunk_document(text, document_title=filename)
        if not chunks:
            logger.warning("No chunks produced from %s", filename)
            return {"case_law_id": None, "chunks_count": 0, "status": "no_chunks"}
        logger.info("Produced %s chunks", len(chunks))

        # Step 4: Embed
        _progress("embedding", 0.55)
        logger.info("Embedding %s chunks...", len(chunks))
        embedded = self._embedder.embed_chunks(chunks)
        logger.info("Embedded %s chunks", len(embedded))

        # Step 5: Store with tenant_id
        _progress("storing", 0.80)
        chunk_dicts = [
            {
                "text": ec.text,
                "embedding": ec.embedding,
                "chunk_index": ec.chunk_index,
                "section_number": ec.section_number,
                "metadata": ec.metadata,
            }
            for ec in embedded
        ]

        case_law_id = self._storage.upsert_document(
            tenant_id=tenant_id,
            file_id=file_id,
            file_name=filename,
            text=text,
            chunks=chunk_dicts,
            content_hash=content_hash,
            source_provider=source_provider,
        )

        _progress("done", 1.0)
        logger.info("Ingestion complete: %s → %s chunks, case_law_id=%s", filename, len(chunks), case_law_id)
        return {
            "case_law_id": case_law_id,
            "chunks_count": len(chunks),
            "status": "completed",
        }

    def get_tenant_documents(self, tenant_id: str) -> list[dict]:
        """List all ingested documents for a tenant."""
        return self._storage.get_tenant_documents(tenant_id)
