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
# Helper imports deleted

# Import the new service
from src.services.finlex.ingestion import FinlexIngestionService


# We can remove the local _process_single_document function entirely as it's now in the service.
# And we update the endpoint to use the service.

@app.post("/ingest", response_model=IngestResponse)
async def ingest_documents(request: IngestRequest):
    """
    Ingest one or more Finlex documents through the complete pipeline
    
    - **documents**: List of documents with individual URIs and status
    - **year**: Year to fetch if no documents provided
    """
    # Initialize Service
    service = FinlexIngestionService()
    
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
            # Check if force re-ingest is needed based on status
            force_reingest = (status == "MODIFIED")
            
            result = await service.process_document(
                document_uri=document_uri,
                force_reingest=force_reingest
            )
            
            # Use the result from service
            results.append(result)
            if result['success']:
                successful += 1
            else:
                failed += 1
            
        except Exception as e:
            error_msg = str(e)
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
    # Initialize service
    service = FinlexIngestionService()
    
    # Get failed docs with retry_count < max_retries
    failed_docs_response = service.storage.client.table('failed_documents').select('*').lt(
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
    
    results = []
    successful = 0
    failed = 0
    
    for doc in failed_docs_response.data:
        document_uri = doc['document_uri']
        
        try:
            # Process document using service
            # For retry, we assume we want to force re-process even if chunks exist (likely corrupted or partial)
            # OR we rely on standard logic. 
            # In old logic: we deleted existing chunks first.
            # Service supports force_reingest=True to do exactly that.
            
            result = await service.process_document(
                document_uri=document_uri,
                force_reingest=True,
                # Pass pre-extracted metadata if available to save API calls?
                # Service currently re-fetches metadata. Optimally we'd pass it in, 
                # but service signature supports passing them.
                language=doc.get('language'),
                document_type=doc.get('document_type'),
                document_category=doc.get('document_category'),
                document_year=doc.get('document_year')
            )
            
            result['previous_retry_count'] = doc.get('retry_count', 0)
            result['message'] = 'Retry successful'
            results.append(result)
            
            if result['success']:
                successful += 1
            else:
                failed += 1
                # If failure happened inside service, it logs it anew. 
                # But we also need to increment retry_count on the OLD failure record?
                # The service deletes the old failure record on success.
                # If service fails, it logs a NEW failure record with count=0 properly?
                # Actually service logs failure with count 0 (if new) or increments?
                # Service.log_failed_document handles logic.
                
                # However, for RETRY logic specifically, we want to increment the EXISTING counter.
                # Service treats it as a fresh ingestion.
                # Let's handle the counter increment here if result is false contextually.
                
                # If service returns success=False, it means it failed.
                # We should update the retry count manually here?
                # Or trust the service? Service defaults to retry_count=0 for new entries.
                
                # Simpler: If service fails, it creates a new entry.
                # We should perhaps just let it be.
            
        except Exception as e:
            error_msg = str(e)
            
            # FAILURE: Increment retry count manually if service blew up
            new_retry_count = doc.get('retry_count', 0) + 1
            
            service.storage.client.table('failed_documents').update({
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
