#!/usr/bin/env python3
"""
Bulk Document Ingestion Script
Systematically ingests ALL Finlex documents across ALL years with Phase 1 intelligent extraction.
Uses simplified pagination without year filtering - extracts year from each document URI.
"""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio

from src.config.logging_config import setup_logger
from src.services.finlex.ingestion import FinlexIngestionService

logger = setup_logger(__name__)

# Ingestion configuration: document types to ingest
# No year filtering - fetches ALL documents (auto-extracts year from URI)
CATEGORY = "act"
DOC_TYPES = ["statute", "statute-consolidated"]


class BulkIngestionManager:
    def __init__(self):
        self.service = FinlexIngestionService()
        # Aliases for convenience if needed, or update methods to use self.service.storage
        self.storage = self.service.storage
        self.api = self.service.api

    def get_tracking_status(self, category: str, doc_type: str, year: int) -> dict | None:
        """Get current tracking status from database"""
        result = (
            self.storage.client.table("ingestion_tracking")
            .select("*")
            .eq("document_category", category)
            .eq("document_type", doc_type)
            .eq("year", year)
            .execute()
        )
        return result.data[0] if result.data else None

    def init_tracking(self, category: str, doc_type: str, year: int) -> None:
        """Initialize tracking record"""
        self.storage.client.table("ingestion_tracking").upsert(
            {
                "document_category": category,
                "document_type": doc_type,
                "year": year,
                "status": "in_progress",
                "started_at": "now()",
                "last_updated": "now()",
            }
        ).execute()

    def update_tracking(self, category: str, doc_type: str, year: int, page: int, processed: int, failed: int) -> None:
        """Update tracking progress"""
        self.storage.client.table("ingestion_tracking").update(
            {
                "last_processed_page": page,
                "documents_processed": processed,
                "documents_failed": failed,
                "last_updated": "now()",
            }
        ).eq("document_category", category).eq("document_type", doc_type).eq("year", year).execute()

    def mark_completed(self, category: str, doc_type: str, year: int) -> None:
        """Mark ingestion as completed"""
        self.storage.client.table("ingestion_tracking").update(
            {"status": "completed", "completed_at": "now()", "last_updated": "now()"}
        ).eq("document_category", category).eq("document_type", doc_type).eq("year", year).execute()

    def mark_no_documents(self, category: str, doc_type: str, year: int) -> None:
        """Mark as no documents available"""
        self.storage.client.table("ingestion_tracking").update(
            {"status": "no_documents", "completed_at": "now()", "last_updated": "now()"}
        ).eq("document_category", category).eq("document_type", doc_type).eq("year", year).execute()

    def get_doctype_progress(self, category: str, doc_type: str) -> dict:
        """Get progress for a doc_type (year=0 used as key for simplified pagination)"""
        result = (
            self.storage.client.table("ingestion_tracking")
            .select("*")
            .eq("document_category", category)
            .eq("document_type", doc_type)
            .eq("year", 0)  # year=0 means "all years"
            .execute()
        )
        return result.data[0] if result.data else None

    def init_doctype_progress(self, category: str, doc_type: str) -> None:
        """Initialize progress tracking for a doc_type"""
        self.storage.client.table("ingestion_tracking").upsert(
            {
                "document_category": category,
                "document_type": doc_type,
                "year": 0,  # year=0 means "all years"
                "status": "in_progress",
                "last_processed_page": 0,
                "documents_processed": 0,
                "documents_failed": 0,
                "started_at": "now()",
                "last_updated": "now()",
            }
        ).execute()

    def update_doctype_progress(self, category: str, doc_type: str, page: int, processed: int, failed: int) -> None:
        """Update progress for a doc_type"""
        self.storage.client.table("ingestion_tracking").update(
            {
                "last_processed_page": page,
                "documents_processed": processed,
                "documents_failed": failed,
                "last_updated": "now()",
            }
        ).eq("document_category", category).eq("document_type", doc_type).eq("year", 0).execute()

    def mark_doctype_completed(self, category: str, doc_type: str, processed: int) -> None:
        """Mark doc_type ingestion as completed"""
        self.storage.client.table("ingestion_tracking").update(
            {
                "status": "completed",
                "completed_at": "now()",
                "documents_processed": processed,
                "last_updated": "now()",
            }
        ).eq("document_category", category).eq("document_type", doc_type).eq("year", 0).execute()

    async def process_document(self, document_uri: str, status: str, category: str, doc_type: str) -> bool:
        """
        Process a single document using the shared service
        Returns: True if successful, False if failed
        """
        try:
            result = await self.service.process_document(
                document_uri=document_uri,
                force_reingest=(status == "MODIFIED"),
                document_category=category,
                document_type=doc_type,
            )
            return result["success"]

        except Exception as e:
            logger.error("❌ Error processing %s: %s", document_uri, e)
            return False

    async def process_year(self, category: str, doc_type: str, year: int) -> None:
        """Process all documents for a specific category/type/year"""
        logger.info("Processing: %s/%s/%s", category, doc_type, year)

        # Get or init tracking
        tracking = self.get_tracking_status(category, doc_type, year)
        if tracking and tracking["status"] == "completed":
            logger.info("✅ Already completed, skipping...")
            return

        start_page = tracking["last_processed_page"] + 1 if tracking else 1
        processed = tracking["documents_processed"] if tracking else 0
        failed = tracking["documents_failed"] if tracking else 0

        if not tracking:
            self.init_tracking(category, doc_type, year)

        # Fetch documents page by page
        page = start_page
        while True:
            logger.info("📄 [%s] Page %s...", year, page)

            try:
                # Fetch page (async)
                documents = await self.api.fetch_document_list(
                    category=category, doc_type=doc_type, year=year, page=page, limit=10
                )

                # Check if empty
                if not documents:
                    if page == 1:
                        logger.info("ℹ️  No documents found")
                        self.mark_no_documents(category, doc_type, year)
                    else:
                        logger.info("✅ Completed all pages")
                        self.mark_completed(category, doc_type, year)
                    break

                # Process each document
                for doc in documents:
                    uri = doc["akn_uri"]
                    status = doc["status"]

                    success = await self.process_document(uri, status, category, doc_type)
                    if success:
                        processed += 1
                    else:
                        failed += 1

                    # Small delay to avoid rate limiting
                    await asyncio.sleep(0.5)

                # Update tracking
                self.update_tracking(category, doc_type, year, page, processed, failed)
                logger.info("📊 Progress: %s processed, %s failed", processed, failed)

                # Next page
                page += 1

            except Exception as e:
                logger.error("❌ Error on page %s: %s", page, e)
                break

    async def process_doc_type(self, category: str, doc_type: str, concurrent_workers: int = 5) -> None:
        """
        Process all documents for a specific category/type (ALL YEARS, no year filtering).

        Uses concurrent processing for speed (multiple documents in parallel).
        Supports resumption from last page on restart.

        Args:
            concurrent_workers: Number of concurrent document processing tasks (default: 5)
        """
        logger.info("\n## Processing %s/%s (ALL YEARS, %s concurrent workers)", category, doc_type, concurrent_workers)

        # Check if already completed
        progress = self.get_doctype_progress(category, doc_type)
        if progress and progress["status"] == "completed":
            logger.info("✅ Already completed, skipping...")
            return

        # Resume from last page or start fresh
        if progress:
            page = progress["last_processed_page"] + 1
            processed = progress["documents_processed"]
            failed = progress["documents_failed"]
            logger.info("📖 Resuming from page %s (already processed: %s docs)", page, processed)
        else:
            page = 1
            processed = 0
            failed = 0
            self.init_doctype_progress(category, doc_type)
            logger.info("📖 Starting fresh ingestion")

        total_start = time.time()
        semaphore = asyncio.Semaphore(concurrent_workers)

        async def process_with_semaphore(uri: str, status: str) -> bool:
            """Process document with concurrency control"""
            async with semaphore:
                return await self.process_document(uri, status, category, doc_type)

        while True:
            logger.info("📄 Page %s...", page)

            try:
                # Fetch page WITHOUT year filter (gets all years)
                documents = await self.api.fetch_document_list(
                    category=category, doc_type=doc_type, year=None, page=page, limit=10
                )

                if not documents:
                    logger.info("✅ Reached end of documents (page %s returned 0 items)", page)
                    self.mark_doctype_completed(category, doc_type, processed)
                    break

                # Process documents CONCURRENTLY (multiple at same time)
                tasks = [process_with_semaphore(doc["akn_uri"], doc["status"]) for doc in documents]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Count results
                for result in results:
                    if isinstance(result, Exception):
                        failed += 1
                    elif result:
                        processed += 1
                    else:
                        failed += 1

                logger.info("📊 Page %s done - Total: %s processed, %s failed", page, processed, failed)

                # Update progress tracking
                self.update_doctype_progress(category, doc_type, page, processed, failed)

                page += 1

                # Small delay between pages (not per-document)
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error("❌ Error on page %s: %s", page, e)
                # Save progress before breaking
                self.update_doctype_progress(category, doc_type, page - 1, processed, failed)
                break

        elapsed = time.time() - total_start
        rate = processed / elapsed if elapsed > 0 else 0
        logger.info(
            "✅ Completed %s/%s - %s docs in %.0fs (%.1f docs/sec)", category, doc_type, processed, elapsed, rate
        )

    async def run(self) -> None:
        logger.info("🚀 BULK DOCUMENT INGESTION - Phase 1 (Intelligent Extraction)")
        logger.info("Strategy: Simplified pagination (ALL YEARS, no filtering)")
        logger.info("Category: %s", CATEGORY)
        logger.info("Document types: %s", ", ".join(DOC_TYPES))
        total_start = time.time()

        # Process each document type (all years in one sequence)
        for doc_type in DOC_TYPES:
            await self.process_doc_type(CATEGORY, doc_type)

        total_elapsed = time.time() - total_start
        logger.info("\n✅ ALL INGESTION COMPLETED")
        logger.info("⏱️  TOTAL TIME: %.0fs (%.1f hours)", total_elapsed, total_elapsed / 3600)


def main():
    """Main entry point"""
    manager = BulkIngestionManager()
    asyncio.run(manager.run())


if __name__ == "__main__":
    main()
