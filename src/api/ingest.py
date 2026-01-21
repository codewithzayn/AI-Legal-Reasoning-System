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


class IngestRequest(BaseModel):
    """Request model for document ingestion"""
    document_uris: Optional[List[str]] = None  # List of URIs for batch processing
    year: Optional[int] = 2025
    status: str = "NEW"  # NEW or MODIFIED
    force_reprocess: bool = False


class IngestResponse(BaseModel):
    """Response model for document ingestion"""
    success: bool
    message: str
    total_documents: int
    successful: int
    failed: int
    results: List[Dict[str, Any]]


@app.post("/ingest", response_model=IngestResponse)
async def ingest_documents(request: IngestRequest):
    """
    Ingest one or more Finlex documents through the complete pipeline
    
    - **document_uris**: List of document URIs to process
    - **year**: Year to fetch if no URIs provided
    - **status**: NEW or MODIFIED
    - **force_reprocess**: Force reprocessing even if exists
    """
    # Initialize services
    api = FinlexAPI()
    parser = XMLParser()
    chunker = LegalDocumentChunker(max_chunk_size=1000, min_chunk_size=100, overlap=50)
    embedder = DocumentEmbedder()
    storage = SupabaseStorage()
    
    # Get list of URIs to process
    uris_to_process = []
    if request.document_uris:
        uris_to_process = request.document_uris
    else:
        # Fetch single statute if no URIs provided
        doc = api.fetch_single_statute(year=request.year)
        uris_to_process = [doc['uri']]
    
    # Process each document
    results = []
    successful = 0
    failed = 0
    
    for document_uri in uris_to_process:
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
            
            if request.status == "NEW" and exists.data:
                results.append({
                    "document_uri": document_uri,
                    "success": True,
                    "message": "Skipped (already exists)",
                    "chunks_stored": 0
                })
                successful += 1
                continue
            
            if request.force_reprocess or (request.status == "MODIFIED" and exists.data):
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
        message=f"Processed {len(uris_to_process)} documents: {successful} successful, {failed} failed",
        total_documents=len(uris_to_process),
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
