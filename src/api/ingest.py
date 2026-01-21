from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uvicorn
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import services
from src.services.finlex_api import FinlexAPI
from src.services.xml_parser import XMLParser
from src.services.chunker import LegalDocumentChunker
from src.services.embedder import DocumentEmbedder
from src.services.supabase import SupabaseStorage

app = FastAPI(title="Finlex Document Ingestion API")


class DocumentItem(BaseModel):
    """Individual document with its own status"""
    document_uri: str
    status: str = "NEW"  # NEW or MODIFIED


class IngestRequest(BaseModel):
    """Request model for document ingestion"""
    documents: Optional[List[DocumentItem]] = None  # List of documents with individual status
    year: Optional[int] = 2025
    force_reprocess: bool = False


class IngestResponse(BaseModel):
    """Response model for document ingestion"""
    success: bool
    message: str
    total_documents: int
    successful: int
    failed: int
    results: List[Dict[str, Any]]


class RetryRequest(BaseModel):
    """Request model for retrying failed documents"""
    max_retries: int = 3


@app.post("/ingest", response_model=IngestResponse)
async def ingest_documents(request: IngestRequest):
    """
    Ingest one or more Finlex documents through the complete pipeline
    
    - **documents**: List of documents with individual URIs and status
    - **year**: Year to fetch if no documents provided
    - **force_reprocess**: Force reprocessing even if exists
    """
    # Initialize services
    api = FinlexAPI()
    parser = XMLParser()
    chunker = LegalDocumentChunker(max_chunk_size=1000, min_chunk_size=100, overlap=50)
    embedder = DocumentEmbedder()
    storage = SupabaseStorage()
    
    # Get list of documents to process
    documents_to_process = []
    if request.documents:
        documents_to_process = request.documents
    else:
        # Fetch single statute if no documents provided
        doc = api.fetch_single_statute(year=request.year)
        documents_to_process = [DocumentItem(document_uri=doc['uri'], status="NEW")]
    
    # Process each document
    results = []
    successful = 0
    failed = 0
    
    for doc_item in documents_to_process:
        document_uri = doc_item.document_uri
        status = doc_item.status
        try:
            # Initialize variables
            language = None
            document_type = None
            document_category = None
            document_year = None
            
            # Step 1: Fetch document
            xml = api.fetch_document_xml(document_uri)
            document_type = api._extract_document_type(document_uri)
            document_category = api._extract_document_category(document_uri)
            document_year = api._extract_year(document_uri)
            language = api._extract_language(document_uri)
            
            # Check if exists
            exists = storage.client.table('legal_chunks').select('id').eq(
                'document_uri', document_uri
            ).limit(1).execute()
            
            if status == "NEW" and exists.data:
                results.append({
                    "document_uri": document_uri,
                    "success": True,
                    "message": "Skipped (already exists)",
                    "chunks_stored": 0
                })
                successful += 1
                continue
            
            if request.force_reprocess or (status == "MODIFIED" and exists.data):
                # Delete existing chunks
                storage.client.table('legal_chunks').delete().eq(
                    'document_uri', document_uri
                ).execute()
            
            # Step 2: Parse XML
            parsed = parser.parse(xml)
            
            # Step 3: Chunk document
            chunks = chunker.chunk_document(
                text=parsed['text'],
                document_uri=document_uri,
                document_title=parsed['title'],
                document_year=document_year,
                document_type=document_type,
                document_category=document_category,
                language=language,
                sections=parsed.get('sections', []),
                attachments=parsed.get('attachments', [])
            )
            
            # Step 4: Generate embeddings
            embedded_chunks = embedder.embed_chunks(chunks)
            
            # Step 5: Store in Supabase
            stored_count = storage.store_chunks(embedded_chunks)
            
            # Step 6: Update tracking
            tracking_check = storage.client.table('ingestion_tracking').select('*').eq(
                'document_category', document_category
            ).eq('document_type', document_type).eq('year', document_year).execute()
            
            if tracking_check.data:
                current_processed = tracking_check.data[0].get('documents_processed', 0) or 0
                storage.client.table('ingestion_tracking').update({
                    'documents_processed': current_processed + 1,
                    'last_updated': 'now()'
                }).eq('document_category', document_category).eq('document_type', document_type).eq('year', document_year).execute()
            else:
                storage.client.table('ingestion_tracking').insert({
                    'document_category': document_category,
                    'document_type': document_type,
                    'year': document_year,
                    'status': 'in_progress',
                    'started_at': 'now()',
                    'last_updated': 'now()',
                    'documents_processed': 1,
                    'documents_failed': 0,
                    'last_processed_page': 1
                }).execute()
            
            # Remove from failed_documents after successful completion
            try:
                storage.client.table('failed_documents').delete().eq(
                    'document_uri', document_uri
                ).execute()
            except:
                pass  # Ignore if not in failed_documents
            
            results.append({
                "document_uri": document_uri,
                "success": True,
                "message": "Ingested successfully",
                "chunks_stored": stored_count,
                "document_title": parsed['title']
            })
            successful += 1
            
        except Exception as e:
            error_msg = str(e)
            
            # Log failure
            try:
                storage.log_failed_document(
                    document_uri=document_uri,
                    error_message=error_msg,
                    error_type='api_error',
                    document_category=document_category if 'document_category' in locals() else None,
                    document_type=document_type if 'document_type' in locals() else None,
                    document_year=document_year if 'document_year' in locals() else None,
                    language=language if 'language' in locals() else None
                )
            except Exception as log_error:
                print(f"  ⚠️  Failed to log error: {str(log_error)}")
            
            results.append({
                "document_uri": document_uri,
                "success": False,
                "message": f"Failed: {error_msg}",
                "chunks_stored": 0
            })
            failed += 1
    
    return IngestResponse(
        success=failed == 0,
        message=f"Processed {len(documents_to_process)} documents: {successful} successful, {failed} failed",
        total_documents=len(documents_to_process),
        successful=successful,
        failed=failed,
        results=results
    )


@app.post("/retry-failed", response_model=IngestResponse)
async def retry_failed_documents(request: RetryRequest):
    """
    Automatically retry all failed documents with retry_count < max_retries
    
    - **max_retries**: Maximum number of retries allowed (default: 3)
    """
    storage = SupabaseStorage()
    
    # Get failed docs with retry_count < max_retries
    failed_docs_response = storage.client.table('failed_documents').select('*').lt(
        'retry_count', request.max_retries
    ).execute()
    
    if not failed_docs_response.data:
        return IngestResponse(
            success=True,
            message="No failed documents to retry",
            total_documents=0,
            successful=0,
            failed=0,
            results=[]
        )
    
    # Initialize services
    api = FinlexAPI()
    parser = XMLParser()
    chunker = LegalDocumentChunker(max_chunk_size=1000, min_chunk_size=100, overlap=50)
    embedder = DocumentEmbedder()
    
    results = []
    successful = 0
    failed = 0
    
    for doc in failed_docs_response.data:
        document_uri = doc['document_uri']
        
        try:
            # Initialize variables
            language = doc.get('language')
            document_type = doc.get('document_type')
            document_category = doc.get('document_category')
            document_year = doc.get('document_year')
            
            # Step 1: Fetch document
            xml = api.fetch_document_xml(document_uri)
            
            # Extract metadata if not available
            if not document_type:
                document_type = api._extract_document_type(document_uri)
            if not document_category:
                document_category = api._extract_document_category(document_uri)
            if not document_year:
                document_year = api._extract_year(document_uri)
            if not language:
                language = api._extract_language(document_uri)
            
            # Delete existing chunks if any
            storage.client.table('legal_chunks').delete().eq(
                'document_uri', document_uri
            ).execute()
            
            # Step 2: Parse XML
            parsed = parser.parse(xml)
            
            # Step 3: Chunk document
            chunks = chunker.chunk_document(
                text=parsed['text'],
                document_uri=document_uri,
                document_title=parsed['title'],
                document_year=document_year,
                document_type=document_type,
                document_category=document_category,
                language=language,
                sections=parsed.get('sections', []),
                attachments=parsed.get('attachments', [])
            )
            
            # Step 4: Generate embeddings
            embedded_chunks = embedder.embed_chunks(chunks)
            
            # Step 5: Store in Supabase
            stored_count = storage.store_chunks(embedded_chunks)
            
            # Step 6: Update tracking
            tracking_check = storage.client.table('ingestion_tracking').select('*').eq(
                'document_category', document_category
            ).eq('document_type', document_type).eq('year', document_year).execute()
            
            if tracking_check.data:
                current_processed = tracking_check.data[0].get('documents_processed', 0) or 0
                storage.client.table('ingestion_tracking').update({
                    'documents_processed': current_processed + 1,
                    'last_updated': 'now()'
                }).eq('document_category', document_category).eq('document_type', document_type).eq('year', document_year).execute()
            else:
                storage.client.table('ingestion_tracking').insert({
                    'document_category': document_category,
                    'document_type': document_type,
                    'year': document_year,
                    'status': 'in_progress',
                    'started_at': 'now()',
                    'last_updated': 'now()',
                    'documents_processed': 1,
                    'documents_failed': 0,
                    'last_processed_page': 1
                }).execute()
            
            # SUCCESS: Remove from failed_documents
            storage.client.table('failed_documents').delete().eq(
                'document_uri', document_uri
            ).execute()
            
            results.append({
                "document_uri": document_uri,
                "success": True,
                "message": "Retry successful",
                "chunks_stored": stored_count,
                "document_title": parsed['title'],
                "previous_retry_count": doc.get('retry_count', 0)
            })
            successful += 1
            
        except Exception as e:
            error_msg = str(e)
            
            # FAILURE: Increment retry count
            new_retry_count = doc.get('retry_count', 0) + 1
            
            storage.client.table('failed_documents').update({
                'retry_count': new_retry_count,
                'last_retry_at': 'now()',
                'error_message': error_msg
            }).eq('document_uri', document_uri).execute()
            
            results.append({
                "document_uri": document_uri,
                "success": False,
                "message": f"Retry failed: {error_msg}",
                "chunks_stored": 0,
                "retry_count": new_retry_count,
                "max_retries_reached": new_retry_count >= request.max_retries
            })
            failed += 1
    
    return IngestResponse(
        success=failed == 0,
        message=f"Retried {len(failed_docs_response.data)} documents: {successful} successful, {failed} failed",
        total_documents=len(failed_docs_response.data),
        successful=successful,
        failed=failed,
        results=results
    )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
