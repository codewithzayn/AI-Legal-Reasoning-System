"""
Client Document Ingestion Service
Orchestrates: download/upload → extract → chunk → embed → store with tenant_id.
Async pipeline with progress callbacks for UI.
"""

import asyncio
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

    async def aingest_bytes(
        self,
        tenant_id: str,
        file_bytes: bytes,
        filename: str,
        source_provider: str = "upload",
        source_file_id: str | None = None,
        on_progress: callable = None,
    ) -> dict:
        """Async ingest a document from raw bytes.

        Args:
            tenant_id: Tenant identifier.
            file_bytes: Raw file content.
            filename: Original filename.
            source_provider: 'upload', 'google_drive', or 'onedrive'.
            source_file_id: External file ID (from drive). Auto-generated if None.
            on_progress: Optional async callback(stage: str, pct: float) for UI progress.

        Returns:
            Dict with 'case_law_id', 'chunks_count', 'status'.

        Raises:
            ValueError: If file size exceeds MAX_UPLOAD_SIZE_MB.
            asyncio.TimeoutError: If ingestion exceeds INGESTION_TIMEOUT_SECONDS.
        """
        file_id = source_file_id or str(uuid.uuid4())

        async def _progress(stage: str, pct: float) -> None:
            if on_progress:
                if asyncio.iscoroutinefunction(on_progress):
                    await on_progress(stage, pct)
                else:
                    on_progress(stage, pct)

        # Check file size before processing
        file_size_mb = len(file_bytes) / (1024 * 1024)
        if file_size_mb > config.MAX_UPLOAD_SIZE_MB:
            logger.error(
                "Document %s exceeds max size: %.2f MB > %d MB", filename, file_size_mb, config.MAX_UPLOAD_SIZE_MB
            )
            raise ValueError(
                f"Document exceeds maximum size of {config.MAX_UPLOAD_SIZE_MB} MB (got {file_size_mb:.2f} MB)"
            )

        try:
            # Wrap the entire pipeline with timeout
            return await asyncio.wait_for(
                self._execute_ingestion_pipeline(tenant_id, file_bytes, filename, source_provider, file_id, _progress),
                timeout=config.INGESTION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as err:
            logger.error("Ingestion timeout for %s after %d seconds", filename, config.INGESTION_TIMEOUT_SECONDS)
            raise asyncio.TimeoutError(
                f"Document ingestion exceeded timeout of {config.INGESTION_TIMEOUT_SECONDS} seconds"
            ) from err

    async def _execute_ingestion_pipeline(
        self,
        tenant_id: str,
        file_bytes: bytes,
        filename: str,
        source_provider: str,
        file_id: str,
        _progress: callable,
    ) -> dict:
        """Internal pipeline execution (extracted for timeout wrapping)."""
        # Step 1: Check idempotency via content hash
        await _progress("hashing", 0.05)
        content_hash = hashlib.sha256(file_bytes).hexdigest()
        doc_exists = await asyncio.to_thread(self._storage.document_exists, tenant_id, content_hash)
        if doc_exists:
            logger.info("Document already ingested (hash match): %s", filename)
            return {"case_law_id": None, "chunks_count": 0, "status": "already_exists"}

        # Step 2: Extract text (PHASE 1: with quality metrics)
        await _progress("extracting", 0.15)
        logger.info("Extracting text from %s (%s bytes)...", filename, len(file_bytes))
        result = await asyncio.to_thread(self._extractor.extract_from_bytes, file_bytes, filename)
        text = result.get("text", "")
        if not text.strip():
            logger.warning("No text extracted from %s", filename)
            return {"case_law_id": None, "chunks_count": 0, "status": "empty_document"}

        # PHASE 1: Log extraction quality
        extraction_confidence = result.get("extraction_confidence", 0.85)
        completeness_score = result.get("completeness_score", 0.80)
        extraction_warnings = result.get("warnings", [])
        has_quality_issues = extraction_confidence < 0.75 or completeness_score < 0.65

        logger.info(
            "Extraction quality: confidence=%.2f, completeness=%.2f, warnings=%s",
            extraction_confidence,
            completeness_score,
            extraction_warnings,
        )
        if has_quality_issues:
            logger.warning("Document has quality issues and may require manual review")

        # Step 3: Chunk
        await _progress("chunking", 0.35)
        logger.info("Chunking %s characters...", len(text))
        chunks = await asyncio.to_thread(self._chunker.chunk_document, text, filename)
        if not chunks:
            logger.warning("No chunks produced from %s", filename)
            return {"case_law_id": None, "chunks_count": 0, "status": "no_chunks"}
        logger.info("Produced %s chunks", len(chunks))

        # Step 4: Embed
        await _progress("embedding", 0.55)
        logger.info("Embedding %s chunks...", len(chunks))
        embedded = await asyncio.to_thread(self._embedder.embed_chunks, chunks)
        logger.info("Embedded %s chunks", len(embedded))

        # Step 5: Store with tenant_id (non-blocking)
        await _progress("storing", 0.80)
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

        # PHASE 1 & 2: Pass quality metrics to storage (in thread)
        case_law_id = await asyncio.to_thread(
            self._storage.upsert_document,
            tenant_id,
            file_id,
            filename,
            text,
            chunk_dicts,
            content_hash,
            source_provider,
            extraction_confidence,
            completeness_score,
            has_quality_issues,
        )

        await _progress("done", 1.0)
        logger.info("Ingestion complete: %s → %s chunks, case_law_id=%s", filename, len(chunks), case_law_id)
        return {
            "case_law_id": case_law_id,
            "chunks_count": len(chunks),
            "status": "completed",
            "extraction_confidence": extraction_confidence,
            "completeness_score": completeness_score,
            "requires_review": has_quality_issues,
        }

    def ingest_bytes(
        self,
        tenant_id: str,
        file_bytes: bytes,
        filename: str,
        source_provider: str = "upload",
        source_file_id: str | None = None,
        on_progress: callable = None,
    ) -> dict:
        """Sync wrapper for aingest_bytes (for backward compatibility).

        NOTE: For new code, use aingest_bytes() instead.
        """
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.aingest_bytes(tenant_id, file_bytes, filename, source_provider, source_file_id, on_progress)
            )
        finally:
            loop.close()

    def get_tenant_documents(self, tenant_id: str) -> list[dict]:
        """List all ingested documents for a tenant."""
        return self._storage.get_tenant_documents(tenant_id)
