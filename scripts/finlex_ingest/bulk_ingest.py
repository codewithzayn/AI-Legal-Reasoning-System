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

from src.services.finlex_api import FinlexAPI
from src.services.xml_parser import XMLParser
from src.services.chunker import LegalDocumentChunker
from src.services.embedder import DocumentEmbedder
from src.services.supabase import SupabaseStorage

load_dotenv()

# Document categories and types to process
CATEGORIES = {
    "act": ["statute-consolidated"]
}

# Year range (only 2026)
START_YEAR = 2025
END_YEAR = 2025


class BulkIngestionManager:
    """Manages bulk ingestion with tracking and resume capability"""
    
    def __init__(self):
        self.api = FinlexAPI()
        self.parser = XMLParser()
        self.chunker = LegalDocumentChunker()
        self.embedder = DocumentEmbedder()
        self.storage = SupabaseStorage()
        
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
    
    def document_exists(self, document_uri: str) -> bool:
        """Check if document already exists in database"""
        result = self.storage.client.table('legal_chunks').select('document_uri').eq(
            'document_uri', document_uri
        ).limit(1).execute()
        
        return len(result.data) > 0
    
    def delete_document_chunks(self, document_uri: str) -> None:
        """Delete all chunks for a document (for MODIFIED status)"""
        self.storage.client.table('legal_chunks').delete().eq(
            'document_uri', document_uri
        ).execute()
        print(f"  🗑️  Deleted old chunks for: {document_uri}")
    
    def process_document(self, document_uri: str, status: str, category: str, doc_type: str) -> bool:
        """
        Process a single document
        
        Returns:
            True if successful, False if failed
        """
        try:
            # Check if exists
            exists = self.document_exists(document_uri)
            
            # Handle based on status
            if status == "NEW" and exists:
                print(f"  ⏭️  Skipping (already processed): {document_uri}")
                return True
            
            if status == "MODIFIED" and exists:
                self.delete_document_chunks(document_uri)
            
            # Fetch XML
            print(f"  📥 Fetching: {document_uri}")
            xml_content = self.api.fetch_document_xml(document_uri)
            
            # Extract metadata from URI
            document_year = self.api._extract_year(document_uri)
            language = self.api._extract_language(document_uri)
            
            # Parse XML
            parsed = self.parser.parse(xml_content)
            
            # Chunk document
            chunks = self.chunker.chunk_document(
                text=parsed['text'],
                document_uri=document_uri,
                document_title=parsed['title'],
                document_year=document_year,
                document_type=doc_type,
                document_category=category,
                language=language,
                sections=parsed.get('sections', []),
                attachments=parsed.get('attachments', [])
            )
            
            # Generate embeddings
            embedded_chunks = self.embedder.embed_chunks(chunks)
            
            # Store in Supabase
            stored = self.storage.store_chunks(embedded_chunks)
            return True
            
        except Exception as e:
            error_msg = str(e)
            print(f"  ❌ Error processing {document_uri}: {error_msg}")
            
            # Log failure to database
            try:
                language = self.api._extract_language(document_uri)
                document_year = self.api._extract_year(document_uri)
                
                # Determine error type
                error_type = 'unknown'
                if 'parse' in error_msg.lower() or 'xml' in error_msg.lower():
                    error_type = 'parse_error'
                elif 'api' in error_msg.lower() or 'request' in error_msg.lower():
                    error_type = 'api_error'
                elif 'embed' in error_msg.lower():
                    error_type = 'embedding_error'
                elif 'storage' in error_msg.lower() or 'database' in error_msg.lower():
                    error_type = 'storage_error'
                
                self.storage.log_failed_document(
                    document_uri=document_uri,
                    error_message=error_msg,
                    error_type=error_type,
                    document_category=category,
                    document_type=doc_type,
                    document_year=document_year,
                    language=language
                )
            except:
                pass  # Don't fail if logging fails
            
            return False
    
    def process_year(self, category: str, doc_type: str, year: int) -> None:
        """Process all documents for a specific category/type/year"""
        print(f"Processing: {category}/{doc_type}/{year}")
        
        # Get or init tracking
        tracking = self.get_tracking_status(category, doc_type, year)
        if tracking and tracking['status'] == 'completed':
            print(f"✅ Already completed, skipping...")
            return
        
        start_page = tracking['last_processed_page'] + 1 if tracking else 1
        processed = tracking['documents_processed'] if tracking else 0
        failed = tracking['documents_failed'] if tracking else 0
        
        if not tracking:
            self.init_tracking(category, doc_type, year)
        
        # Fetch documents page by page
        page = start_page
        while True:
            print(f"\n📄 Page {page}...")
            
            try:
                # Fetch page
                documents = self.api.fetch_document_list(
                    category=category,
                    doc_type=doc_type,
                    year=year,
                    page=page,
                    limit=10
                )
                
                # Check if empty
                if not documents:
                    if page == 1:
                        print(f"  ℹ️  No documents found")
                        self.mark_no_documents(category, doc_type, year)
                    else:
                        print(f"  ✅ Completed all pages")
                        self.mark_completed(category, doc_type, year)
                    break
                
                # Process each document
                for doc in documents:
                    uri = doc['akn_uri']
                    status = doc['status']
                    
                    success = self.process_document(uri, status, category, doc_type)
                    if success:
                        processed += 1
                    else:
                        failed += 1
                    
                    # Small delay to avoid rate limiting
                    time.sleep(0.5)
                
                # Update tracking
                self.update_tracking(category, doc_type, year, page, processed, failed)
                print(f"  📊 Progress: {processed} processed, {failed} failed")
                
                # Next page
                page += 1
                
            except Exception as e:
                print(f"  ❌ Error on page {page}: {str(e)}")
                break
    
    def run(self) -> None:
        print("🚀 BULK DOCUMENT INGESTION")
        print(f"Years: {START_YEAR} → {END_YEAR}")
        print(f"Categories: {list(CATEGORIES.keys())}")
        total_start = time.time()
        
        # Process each year (newest first)
        for year in range(START_YEAR, END_YEAR - 1, -1):
            print(f"# YEAR: {year}")
            
            # Process each category/type
            for category, doc_types in CATEGORIES.items():
                for doc_type in doc_types:
                    self.process_year(category, doc_type, year)
        
        total_elapsed = time.time() - total_start
        print(f"✅ BULK INGESTION COMPLETED")
        print(f"⏱️  TOTAL TIME: {total_elapsed:.2f}s")


def main():
    """Main entry point"""
    manager = BulkIngestionManager()
    manager.run()


if __name__ == "__main__":
    main()
