from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uvicorn
import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import services
from src.services.finlex_api import FinlexAPI
from src.services.xml_parser import XMLParser
from src.services.chunker import LegalDocumentChunker
from src.services.embedder import DocumentEmbedder
from src.services.supabase import SupabaseStorage
from src.services.pdf_extractor import PDFExtractor
from src.config.logging_config import setup_logger
from src.config.settings import config
logger = setup_logger(__name__)
app = FastAPI(title="Finlex Document Ingestion API")


class DocumentItem(BaseModel):
    """Individual document with its own status"""
    document_uri: str
    status: str = "NEW"  # NEW or MODIFIED


class IngestRequest(BaseModel):
    """Request model for document ingestion"""
    documents: Optional[List[DocumentItem]] = None  # List of documents with individual status
    year: Optional[int] = 2025

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

async def _process_single_document(
    document_uri: str,
    api: FinlexAPI,
    parser: XMLParser,
    chunker: LegalDocumentChunker,
    embedder: DocumentEmbedder,
    storage: SupabaseStorage,
    language: str = None,
    document_type: str = None,
    document_category: str = None,
    document_year: int = None
) -> Dict[str, Any]:
    """
    Process a single document through the complete ingestion pipeline.
    
    Args:
        document_uri: URI of the document to process
        api: FinlexAPI instance
        parser: XMLParser instance
        chunker: LegalDocumentChunker instance
        embedder: DocumentEmbedder instance
        storage: SupabaseStorage instance
        language: Optional pre-extracted language
        document_type: Optional pre-extracted document type
        document_category: Optional pre-extracted document category
        document_year: Optional pre-extracted document year
        
    Returns:
        Dict with success status, message, chunks_stored, etc.
    """
    # Step 1: Fetch document (async)
    xml = await api.fetch_document_xml(document_uri)
    
    # Extract metadata if not provided
    if not document_type:
        document_type = api._extract_document_type(document_uri)
    if not document_category:
        document_category = api._extract_document_category(document_uri)
    if not document_year:
        document_year = api._extract_year(document_uri)
    if not language:
        language = api._extract_language(document_uri)
    
    document_number = api.extract_document_number(document_uri)
    
    # Step 2: Parse XML
    parsed = parser.parse(xml, language=language, document_uri=document_uri)
    
    # Handle PDF-only documents
    if parsed.get('is_pdf_only', False):
        pdf_filename = parsed.get('pdf_ref', 'main.pdf')
        pdf_url = f"{document_uri}/{pdf_filename}"
        
        pdf_extractor = PDFExtractor()
        pdf_data = pdf_extractor.extract_from_url(pdf_url)
        
        parsed['text'] = pdf_data['text']
        parsed['length'] = pdf_data['char_count']
        parsed['pdf_metadata'] = {
            'pdf_url': pdf_url,
            'page_count': pdf_data['page_count'],
            'source_type': 'pdf'
        }
    
    # Step 3: Handle embedded PDF links (e.g. for judgments) - PARALLEL DOWNLOAD
    if parsed.get('pdf_links'):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        # Reuse single PDFExtractor instance
        pdf_extractor = PDFExtractor()
        pdf_urls = [f"{document_uri}/{pdf_rel_path}" for pdf_rel_path in parsed['pdf_links']]
        
        def extract_pdf(pdf_url: str) -> Dict[str, Any]:
            """Helper for parallel PDF extraction"""
            try:
                pdf_data = pdf_extractor.extract_from_url(pdf_url)
                return {'success': True, 'url': pdf_url, 'data': pdf_data}
            except Exception as e:
                logger.warning(f"Failed to extract embedded PDF {pdf_url}: {e}")
                return {'success': False, 'url': pdf_url, 'error': str(e)}
        
        # Download PDFs in parallel (max 4 workers)
        with ThreadPoolExecutor(max_workers=config.PDF_MAX_WORKERS) as executor:
            futures = {executor.submit(extract_pdf, url): url for url in pdf_urls}
            
            for future in as_completed(futures):
                result = future.result()
                if result['success']:
                    pdf_data = result['data']
                    parsed['text'] += f"\n\n[PDF CONTENT START]\n{pdf_data['text']}\n[PDF CONTENT END]"
                    parsed['length'] += pdf_data['char_count']
                    
                    if 'pdf_metadata' not in parsed:
                        parsed['pdf_metadata'] = []
                    elif isinstance(parsed['pdf_metadata'], dict):
                        parsed['pdf_metadata'] = [parsed['pdf_metadata']]
                    
                    parsed['pdf_metadata'].append({
                        'pdf_url': result['url'],
                        'page_count': pdf_data['page_count'],
                        'source_type': 'embedded_pdf'
                    })
    
    # Step 4: Chunk document
    chunks = chunker.chunk_document(
        text=parsed['text'],
        document_uri=document_uri,
        document_title=parsed['title'],
        document_year=document_year,
        document_type=document_type,
        document_category=document_category,
        language=language,
        document_number=document_number,
        sections=parsed.get('sections', []),
        attachments=parsed.get('attachments', [])
    )
    
    # Add PDF metadata to chunks if available
    pdf_metadata = parsed.get('pdf_metadata')
    if pdf_metadata:
        if isinstance(pdf_metadata, dict):
            pdf_metadata = [pdf_metadata]
        
        for chunk in chunks:
            if pdf_metadata:
                chunk.metadata.update(pdf_metadata[0])
            chunk.metadata['pdf_files'] = pdf_metadata
    
    # Step 5: Generate embeddings
    embedded_chunks = embedder.embed_chunks(chunks)
    
    # Step 6: Store in Supabase
    stored_count = storage.store_chunks(embedded_chunks)
    
    # Step 7: Update tracking
    tracking_check = storage.client.table('ingestion_tracking').select('*').eq(
        'document_category', document_category
    ).eq('document_type', document_type).eq('year', document_year).execute()
    
    if tracking_check.data:
        current_processed = tracking_check.data[0].get('documents_processed', 0) or 0
        storage.client.table('ingestion_tracking').update({
            'documents_processed': current_processed + 1,
            'status': 'completed',
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
    
    # Remove from failed_documents if exists
    try:
        storage.client.table('failed_documents').delete().eq(
            'document_uri', document_uri
        ).execute()
    except:
        pass
    
    return {
        "document_uri": document_uri,
        "success": True,
        "message": "Ingested successfully",
        "chunks_stored": stored_count,
        "document_title": parsed['title'],
        "document_type": document_type,
        "document_category": document_category,
        "document_year": document_year,
        "language": language
    }

@app.post("/ingest", response_model=IngestResponse)
async def ingest_documents(request: IngestRequest):
    """
    Ingest one or more Finlex documents through the complete pipeline
    
    - **documents**: List of documents with individual URIs and status
    - **year**: Year to fetch if no documents provided
    """
    # Initialize services
    api = FinlexAPI()
    parser = XMLParser()
    chunker = LegalDocumentChunker(
        max_chunk_size=config.CHUNK_SIZE, 
        min_chunk_size=config.CHUNK_MIN_SIZE, 
        overlap=config.CHUNK_OVERLAP
    )
    embedder = DocumentEmbedder()
    storage = SupabaseStorage()
    
    # Get list of documents to process
    if not request.documents:
        raise HTTPException(status_code=400, detail="No documents provided. Please specify documents list.")
    documents_to_process = request.documents
    
    # Process each document
    results = []
    successful = 0
    failed = 0
    
    for doc_item in documents_to_process:
        document_uri = doc_item.document_uri
        status = doc_item.status
        try:
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
            
            if status == "MODIFIED" and exists.data:
                # Delete existing chunks
                storage.client.table('legal_chunks').delete().eq(
                    'document_uri', document_uri
                ).execute()
            
            # Process document using shared helper
            result = await _process_single_document(
                document_uri=document_uri,
                api=api,
                parser=parser,
                chunker=chunker,
                embedder=embedder,
                storage=storage
            )
            
            results.append(result)
            successful += 1
            
        except Exception as e:
            error_msg = str(e)
            
            # Log failure
            try:
                storage.log_failed_document(
                    document_uri=document_uri,
                    error_message=error_msg,
                    error_type='api_error'
                )
            except Exception as log_error:
                logger.error(f"Failed to log error: {log_error}")
            
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
    chunker = LegalDocumentChunker(
        max_chunk_size=config.CHUNK_SIZE, 
        min_chunk_size=config.CHUNK_MIN_SIZE, 
        overlap=config.CHUNK_OVERLAP
    )
    embedder = DocumentEmbedder()
    
    results = []
    successful = 0
    failed = 0
    
    for doc in failed_docs_response.data:
        document_uri = doc['document_uri']
        
        try:
            # Delete existing chunks if any
            storage.client.table('legal_chunks').delete().eq(
                'document_uri', document_uri
            ).execute()
            
            # Process document using shared helper (uses pre-extracted metadata if available)
            result = await _process_single_document(
                document_uri=document_uri,
                api=api,
                parser=parser,
                chunker=chunker,
                embedder=embedder,
                storage=storage,
                language=doc.get('language'),
                document_type=doc.get('document_type'),
                document_category=doc.get('document_category'),
                document_year=doc.get('document_year')
            )
            
            result['previous_retry_count'] = doc.get('retry_count', 0)
            result['message'] = 'Retry successful'
            results.append(result)
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
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
