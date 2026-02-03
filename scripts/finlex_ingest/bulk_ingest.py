#!/usr/bin/env python3
"""
Bulk Document Ingestion Script
Systematically ingests all Finlex documents (2017-2026) with tracking and resume capability
"""

import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config.logging_config import setup_logger
import asyncio
from src.services.finlex.ingestion import FinlexIngestionService

class BulkIngestionManager:
    def __init__(self):
        self.service = FinlexIngestionService()
        # Aliases for convenience if needed, or update methods to use self.service.storage
        self.storage = self.service.storage
        self.api = self.service.api
        
    def get_tracking_status(self, category: str, doc_type: str, year: int) -> Optional[Dict]:
        """Get current tracking status from database"""
        result = self.storage.client.table('ingestion_tracking').select('*').eq(
            'document_category', category
        ).eq('document_type', doc_type).eq('year', year).execute()
        return result.data[0] if result.data else None
    
    def init_tracking(self, category: str, doc_type: str, year: int) -> None:
        """Initialize tracking record"""
        self.storage.client.table('ingestion_tracking').upsert({
            'document_category': category,
            'document_type': doc_type,
            'year': year,
            'status': 'in_progress',
            'started_at': 'now()',
            'last_updated': 'now()'
        }).execute()
    
    def update_tracking(self, category: str, doc_type: str, year: int, 
                       page: int, processed: int, failed: int) -> None:
        """Update tracking progress"""
        self.storage.client.table('ingestion_tracking').update({
            'last_processed_page': page,
            'documents_processed': processed,
            'documents_failed': failed,
            'last_updated': 'now()'
        }).eq('document_category', category).eq('document_type', doc_type).eq('year', year).execute()
    
    def mark_completed(self, category: str, doc_type: str, year: int) -> None:
        """Mark ingestion as completed"""
        self.storage.client.table('ingestion_tracking').update({
            'status': 'completed',
            'completed_at': 'now()',
            'last_updated': 'now()'
        }).eq('document_category', category).eq('document_type', doc_type).eq('year', year).execute()
    
    def mark_no_documents(self, category: str, doc_type: str, year: int) -> None:
        """Mark as no documents available"""
        self.storage.client.table('ingestion_tracking').update({
            'status': 'no_documents',
            'completed_at': 'now()',
            'last_updated': 'now()'
        }).eq('document_category', category).eq('document_type', doc_type).eq('year', year).execute()
    
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
                document_type=doc_type
            )
            return result['success']
            
        except Exception as e:
            logger.error(f"❌ Error processing {document_uri}: {e}")
            return False
    
    async def process_year(self, category: str, doc_type: str, year: int) -> None:
        """Process all documents for a specific category/type/year"""
        logger.info(f"Processing: {category}/{doc_type}/{year}")
        
        # Get or init tracking
        tracking = self.get_tracking_status(category, doc_type, year)
        if tracking and tracking['status'] == 'completed':
            logger.info(f"✅ Already completed, skipping...")
            return
        
        start_page = tracking['last_processed_page'] + 1 if tracking else 1
        processed = tracking['documents_processed'] if tracking else 0
        failed = tracking['documents_failed'] if tracking else 0
        
        if not tracking:
            self.init_tracking(category, doc_type, year)
        
        # Fetch documents page by page
        page = start_page
        while True:
            logger.info(f"📄 Page {page}...")
            
            try:
                # Fetch page (async)
                documents = await self.api.fetch_document_list(
                    category=category,
                    doc_type=doc_type,
                    year=year,
                    page=page,
                    limit=10
                )
                
                # Check if empty
                if not documents:
                    if page == 1:
                        logger.info(f"ℹ️  No documents found")
                        self.mark_no_documents(category, doc_type, year)
                    else:
                        logger.info(f"✅ Completed all pages")
                        self.mark_completed(category, doc_type, year)
                    break
                
                # Process each document
                for doc in documents:
                    uri = doc['akn_uri']
                    status = doc['status']
                    
                    success = await self.process_document(uri, status, category, doc_type)
                    if success:
                        processed += 1
                    else:
                        failed += 1
                    
                    # Small delay to avoid rate limiting
                    await asyncio.sleep(0.5)
                
                # Update tracking
                self.update_tracking(category, doc_type, year, page, processed, failed)
                logger.info(f"📊 Progress: {processed} processed, {failed} failed")
                
                # Next page
                page += 1
                
            except Exception as e:
                logger.error(f"❌ Error on page {page}: {str(e)}")
                break
    
    async def run(self) -> None:
        logger.info("🚀 BULK DOCUMENT INGESTION")
        logger.info(f"Years: {START_YEAR} → {END_YEAR}")
        logger.info(f"Categories: {list(CATEGORIES.keys())}")
        total_start = time.time()
        
        # Process each year (newest first)
        for year in range(START_YEAR, END_YEAR - 1, -1):
            logger.info(f"# YEAR: {year}")
            
            # Process each category/type
            for category, doc_types in CATEGORIES.items():
                for doc_type in doc_types:
                    await self.process_year(category, doc_type, year)
        
        total_elapsed = time.time() - total_start
        logger.info(f"✅ BULK INGESTION COMPLETED")
        logger.info(f"⏱️  TOTAL TIME: {total_elapsed:.2f}s")


def main():
    """Main entry point"""
    manager = BulkIngestionManager()
    asyncio.run(manager.run())


if __name__ == "__main__":
    main()
