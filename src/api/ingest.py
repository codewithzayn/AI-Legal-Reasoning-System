"""
Document Ingestion API
FastAPI endpoint for manual document processing
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import sys
from pathlib import Path
import uvicorn

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.services.finlex_api import FinlexAPI
from src.services.xml_parser import XMLParser
from src.services.chunker import LegalDocumentChunker
from src.services.embedder import DocumentEmbedder
from src.services.supabase import SupabaseStorage

app = FastAPI(title="Finlex Document Ingestion API")


class IngestRequest(BaseModel):
    """Request model for document ingestion"""
    document_uri: Optional[str] = None
    year: Optional[int] = 2025
    status: str = "NEW"  # NEW or MODIFIED
    force_reprocess: bool = False


class IngestResponse(BaseModel):
    """Response model for document ingestion"""
    success: bool
    message: str
    document_uri: str
    chunks_stored: int
    document_title: str


@app.post("/ingest", response_model=IngestResponse)
async def ingest_document(request: IngestRequest):
    """
    Ingest a Finlex document through the complete pipeline
    
    - **document_uri**: Specific document URI (optional, will fetch from year if not provided)
    - **year**: Year to fetch document from (default: 2025)
    - **force_reprocess**: Delete existing chunks and re-process (default: false)
    """
    try:
        # Initialize services
        api = FinlexAPI()
        parser = XMLParser()
        chunker = LegalDocumentChunker(
            max_chunk_size=1000,
            min_chunk_size=100,
            overlap=50
        )
        embedder = DocumentEmbedder()
        storage = SupabaseStorage()
        
        # Initialize variables for error handler
        language = None
        document_uri = None
        document_type = None
        document_category = None
        document_year = None
        
        # Step 1: Fetch document
        if request.document_uri:
            # Fetch specific document
            xml = api.fetch_document_xml(request.document_uri)
            document_uri = request.document_uri
            document_type = api._extract_document_type(document_uri)
            document_category = api._extract_document_category(document_uri)
            document_year = api._extract_year(document_uri)
        else:
            # Fetch single statute from year
            doc = api.fetch_single_statute(year=request.year)
            xml = doc['xml']
            document_uri = doc['uri']
            document_type = doc['document_type']
            document_category = doc['document_category']
            document_year = doc['document_year']
        
        # Extract language from URI
        language = api._extract_language(document_uri)
        print(language)
        # Check if exists and handle force_reprocess
        if request.force_reprocess:
            # Delete existing chunks
            storage.client.table('legal_chunks').delete().eq(
                'document_uri', document_uri
            ).execute()
        
        # Check if document exists
        exists_result = storage.client.table('legal_chunks').select('document_uri').eq(
            'document_uri', document_uri
        ).limit(1).execute()
        exists = len(exists_result.data) > 0
        # Handle based on status
        if request.status == "NEW" and exists:
            return IngestResponse(
                success=True,
                message="Document already exists, skipped",
                document_uri=document_uri,
                chunks_stored=0,
                document_title="Skipped"
            )
        
        if request.status == "MODIFIED" and exists:
            # Delete old chunks
            storage.client.table('legal_chunks').delete().eq(
                'document_uri', document_uri
            ).execute()
        
        # Step 2: Parse XML
        parsed = parser.parse(xml)
        
        # Extract category and type from URI
        if not request.document_uri:
            pass
        
        # Update tracking if exists (don't create new)
        tracking_check = storage.client.table('ingestion_tracking').select('*').eq(
            'document_category', document_category
        ).eq('document_type', document_type).eq('year', document_year).execute()
        
        if tracking_check.data:
            # Update existing tracking
            storage.client.table('ingestion_tracking').update({
                'status': 'in_progress',
                'last_updated': 'now()'
            }).eq('document_category', document_category).eq('document_type', document_type).eq('year', document_year).execute()
        print("language", language)
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
        
        # Update tracking: mark as completed (only if exists)
        if tracking_check.data:
            current_processed = tracking_check.data[0]['documents_processed'] if tracking_check.data[0]['documents_processed'] else 0
            
            storage.client.table('ingestion_tracking').update({
                'documents_processed': current_processed + 1,
                'status': 'completed',
                'completed_at': 'now()',
                'last_updated': 'now()'
            }).eq('document_category', document_category).eq('document_type', document_type).eq('year', document_year).execute()
        
        return IngestResponse(
            success=True,
            message="Document ingested successfully",
            document_uri=document_uri,
            chunks_stored=stored_count,
            document_title=parsed['title']
        )
        
    except Exception as e:
        error_msg = str(e)
        # Log failure
        # try:
        #     storage.log_failed_document(
        #         document_uri=locals().get('document_uri', request.document_uri),
        #         error_message=error_msg,
        #         error_type='api_error',
        #         document_category=locals().get('document_category'),
        #         document_type=locals().get('document_type'),
        #         document_year=locals().get('document_year'),
        #         language=locals().get('language')
        #     )
        # except:
        #     pass
        
        raise HTTPException(status_code=500, detail=error_msg)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "Finlex Document Ingestion API"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
