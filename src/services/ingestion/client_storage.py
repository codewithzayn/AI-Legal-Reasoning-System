"""
Client Document Storage
Stores tenant-scoped documents into case_law + case_law_sections tables
and tracks them in client_documents.
"""

import os

from supabase import Client, create_client

from src.config.logging_config import setup_logger

logger = setup_logger(__name__)


class ClientDocumentStorage:
    """Stores client documents with tenant isolation."""

    def __init__(self) -> None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY required")
        self._client: Client = create_client(url, key)

    def upsert_document(
        self,
        tenant_id: str,
        file_id: str,
        file_name: str,
        text: str,
        chunks: list[dict],
        content_hash: str,
        source_provider: str = "upload",
        extraction_confidence: float = 0.85,
        completeness_score: float = 0.80,
        requires_review: bool = False,
    ) -> int:
        """Store a client document and its chunks.

        Args:
            tenant_id: Tenant identifier.
            file_id: Unique file identifier (drive ID or generated).
            file_name: Original file name.
            text: Full extracted text (stored in case_law.judgment).
            chunks: List of dicts with 'text', 'embedding', 'chunk_index',
                    'section_number', 'metadata'.
            content_hash: SHA-256 hash for idempotency.
            source_provider: 'upload', 'google_drive', or 'onedrive'.
            extraction_confidence: Quality score of extraction (0.0-1.0).
            completeness_score: Completeness of extracted data (0.0-1.0).
            requires_review: True if document has quality issues.

        Returns:
            case_law row ID.
        """
        case_id = f"CLIENT:{tenant_id}:{file_id}"

        # Check if already ingested with same hash
        existing = (
            self._client.table("client_documents")
            .select("id, case_law_id")
            .eq("tenant_id", tenant_id)
            .eq("content_hash", content_hash)
            .limit(1)
            .execute()
        )
        if existing.data:
            logger.info("Document already ingested (same hash): %s", file_name)
            return existing.data[0].get("case_law_id", 0)

        # Upsert case_law row
        file_ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "unknown"
        case_law_data = {
            "case_id": case_id,
            "title": file_name,
            "court_type": "client_document",
            "decision_type": "client_document",
            "tenant_id": tenant_id,
            "judgment": text[:50000] if text else "",  # truncate to fit column
            "primary_language": "fi",
        }

        # Try to find existing
        existing_case = self._client.table("case_law").select("id").eq("case_id", case_id).limit(1).execute()

        if existing_case.data:
            case_law_id = existing_case.data[0]["id"]
            self._client.table("case_law").update(case_law_data).eq("id", case_law_id).execute()
            # Delete old sections for this case
            self._client.table("case_law_sections").delete().eq("case_law_id", case_law_id).execute()
            logger.info("Updated existing case_law row: %s", case_id)
        else:
            result = self._client.table("case_law").insert(case_law_data).execute()
            case_law_id = result.data[0]["id"]
            logger.info("Created case_law row: %s (id=%s)", case_id, case_law_id)

        # Insert chunks into case_law_sections with CLIENT DOCUMENT MARKER
        sections_data = []
        for chunk in chunks:
            sections_data.append(
                {
                    "case_law_id": case_law_id,
                    "content": chunk["text"],
                    "section_type": chunk.get("metadata", {}).get("type", "content"),
                    "section_title": chunk.get("section_number", ""),
                    "embedding": chunk.get("embedding"),
                    "tenant_id": tenant_id,
                    "is_client_document": True,  # PHASE 2: MARK AS CLIENT DOC
                }
            )

        if sections_data:
            # Insert in batches of 50
            for i in range(0, len(sections_data), 50):
                batch = sections_data[i : i + 50]
                self._client.table("case_law_sections").insert(batch).execute()
            logger.info("Inserted %s sections for %s", len(sections_data), case_id)

        # Track in client_documents (PHASE 1 & 2: with quality metrics)
        doc_status = "pending_review" if requires_review else "completed"
        self._client.table("client_documents").insert(
            {
                "tenant_id": tenant_id,
                "source_provider": source_provider,
                "source_file_id": file_id,
                "file_name": file_name,
                "file_type": file_ext,
                "status": doc_status,
                "content_hash": content_hash,
                "chunks_stored": len(chunks),
                "case_law_id": case_law_id,
                "extraction_confidence": extraction_confidence,
                "completeness_score": completeness_score,
                "requires_review": requires_review,
            }
        ).execute()

        return case_law_id

    def get_tenant_documents(self, tenant_id: str) -> list[dict]:
        """List all documents for a tenant."""
        result = (
            self._client.table("client_documents")
            .select("id, file_name, file_type, status, chunks_stored, created_at")
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    def document_exists(self, tenant_id: str, content_hash: str) -> bool:
        """Check if a document with this hash already exists for the tenant."""
        result = (
            self._client.table("client_documents")
            .select("id")
            .eq("tenant_id", tenant_id)
            .eq("content_hash", content_hash)
            .limit(1)
            .execute()
        )
        return bool(result.data)
