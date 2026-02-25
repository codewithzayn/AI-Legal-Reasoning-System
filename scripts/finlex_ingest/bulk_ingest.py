#!/usr/bin/env python3
"""
Bulk Document Ingestion Script
Systematically ingests ALL Finlex documents across ALL years with Phase 1 intelligent extraction.
Uses simplified pagination without year filtering - extracts year from each document URI.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio

from src.config.logging_config import setup_logger
from src.services.finlex.ingestion import FinlexIngestionService

logger = setup_logger(__name__)

CATEGORY = "act"
DOC_TYPES = ["statute", "statute-consolidated"]


class BulkIngestionManager:
    def __init__(self):
        self.service = FinlexIngestionService()
        self.storage = self.service.storage
        self.api = self.service.api

    def get_doctype_progress(self, category: str, doc_type: str) -> dict:
        """Get progress for a doc_type (year=0 used as key for simplified pagination)"""
        result = (
            self.storage.client.table("ingestion_tracking")
            .select("*")
            .eq("document_category", category)
            .eq("document_type", doc_type)
            .eq("year", 0)
            .execute()
        )
        return result.data[0] if result.data else None

    def init_doctype_progress(self, category: str, doc_type: str) -> None:
        """Initialize progress tracking for a doc_type"""
        self.storage.client.table("ingestion_tracking").upsert(
            {
                "document_category": category,
                "document_type": doc_type,
                "year": 0,
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
        """Process a single document. Returns True if successful, False if failed."""
        try:
            result = await self.service.process_document(
                document_uri=document_uri,
                force_reingest=(status == "MODIFIED"),
                document_category=category,
                document_type=doc_type,
            )
            return result["success"]
        except Exception as e:
            logger.debug("Error processing %s: %s", document_uri, e)
            return False

    async def process_doc_type(
        self, category: str, doc_type: str, concurrent_workers: int = 10, page_size: int = 10
    ) -> None:
        """
        Process all documents for a category/type across ALL YEARS.

        Uses concurrent processing (multiple documents in parallel) and supports
        resumption from last page on restart.

        Args:
            category: Document category (act, judgment, doc)
            doc_type: Document type (statute, statute-consolidated, etc.)
            concurrent_workers: Number of concurrent processing tasks (default: 10)
            page_size: Documents per API page (default: 10, API maximum)
        """
        logger.info("Processing %s/%s (all years, %d workers)", category, doc_type, concurrent_workers)

        progress = self.get_doctype_progress(category, doc_type)
        if progress and progress["status"] == "completed":
            total_pages = progress.get("last_processed_page", 0)
            logger.info(
                "  Already completed: %d pages, %d docs processed", total_pages, progress.get("documents_processed", 0)
            )
            return

        if progress:
            page = progress["last_processed_page"] + 1
            processed = progress["documents_processed"]
            failed = progress["documents_failed"]
            logger.info("  Resuming from page %d (progress: %d docs, %d failed)", page, processed, failed)
        else:
            page = 1
            processed = 0
            failed = 0
            self.init_doctype_progress(category, doc_type)
            logger.info("  Starting fresh ingestion")

        total_start = time.time()
        total_pages = 0
        semaphore = asyncio.Semaphore(concurrent_workers)

        async def process_with_semaphore(uri: str, status: str) -> bool:
            async with semaphore:
                return await self.process_document(uri, status, category, doc_type)

        while True:
            logger.debug("Page %d", page)

            try:
                documents = await self.api.fetch_document_list(
                    category=category, doc_type=doc_type, year=None, page=page, limit=page_size
                )

                if not documents:
                    total_pages = page - 1
                    self.mark_doctype_completed(category, doc_type, processed)
                    break

                tasks = [process_with_semaphore(doc["akn_uri"], doc["status"]) for doc in documents]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, Exception):
                        failed += 1
                    elif result:
                        processed += 1
                    else:
                        failed += 1

                self.update_doctype_progress(category, doc_type, page, processed, failed)
                page += 1
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error("Error on page %d: %s", page, e)
                total_pages = page - 1
                self.update_doctype_progress(category, doc_type, page - 1, processed, failed)
                break

        elapsed = time.time() - total_start
        rate = processed / elapsed if elapsed > 0 else 0
        logger.info(
            "Completed %s/%s: %d pages, %d docs (%.0fs, %.2f docs/sec)",
            category,
            doc_type,
            total_pages,
            processed,
            elapsed,
            rate,
        )

    async def run(self) -> None:
        logger.info("Bulk ingestion started: %s [%s]", CATEGORY, ", ".join(DOC_TYPES))
        total_start = time.time()
        stats = {}

        for doc_type in DOC_TYPES:
            await self.process_doc_type(CATEGORY, doc_type)
            progress = self.get_doctype_progress(CATEGORY, doc_type)
            if progress:
                stats[doc_type] = {
                    "pages": progress.get("last_processed_page", 0),
                    "docs": progress.get("documents_processed", 0),
                    "failed": progress.get("documents_failed", 0),
                }

        total_elapsed = time.time() - total_start

        # Summary with comparative stats
        total_pages = sum(s["pages"] for s in stats.values())
        total_docs = sum(s["docs"] for s in stats.values())
        total_failed = sum(s["failed"] for s in stats.values())

        logger.info("=" * 60)
        logger.info("Bulk ingestion completed")
        for doc_type, stat in stats.items():
            logger.info("  %s: %d pages, %d docs (+%d failed)", doc_type, stat["pages"], stat["docs"], stat["failed"])
        logger.info("=" * 60)
        logger.info(
            "Total: %d pages, %d docs, %d failed in %.0fs (%.2f hours)",
            total_pages,
            total_docs,
            total_failed,
            total_elapsed,
            total_elapsed / 3600,
        )


def main():
    """Main entry point"""
    manager = BulkIngestionManager()
    asyncio.run(manager.run())


if __name__ == "__main__":
    main()
