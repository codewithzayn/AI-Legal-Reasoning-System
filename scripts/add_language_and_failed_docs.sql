-- Add language support and failed document tracking
-- Run this migration in Supabase SQL editor

-- 1. Add language column to legal_chunks
ALTER TABLE legal_chunks 
ADD COLUMN IF NOT EXISTS language VARCHAR(10) DEFAULT 'fin';

-- Create index for language filtering
CREATE INDEX IF NOT EXISTS idx_legal_chunks_language ON legal_chunks(language);

-- 2. Create failed_documents table
CREATE TABLE IF NOT EXISTS failed_documents (
    id BIGSERIAL PRIMARY KEY,
    document_uri TEXT NOT NULL,
    document_category VARCHAR(50),
    document_type VARCHAR(100),
    document_year INTEGER,
    language VARCHAR(10),
    error_message TEXT,
    error_type VARCHAR(100),
    failed_at TIMESTAMPTZ DEFAULT NOW(),
    retry_count INTEGER DEFAULT 0,
    last_retry_at TIMESTAMPTZ,
    CONSTRAINT failed_documents_unique_uri UNIQUE(document_uri)
);

-- Create indexes for failed_documents
CREATE INDEX IF NOT EXISTS idx_failed_docs_category_type_year 
ON failed_documents(document_category, document_type, document_year);

CREATE INDEX IF NOT EXISTS idx_failed_docs_language 
ON failed_documents(language);

CREATE INDEX IF NOT EXISTS idx_failed_docs_failed_at 
ON failed_documents(failed_at DESC);

-- Add comment
COMMENT ON TABLE failed_documents IS 'Tracks documents that failed during ingestion for retry and debugging';
COMMENT ON COLUMN failed_documents.retry_count IS 'Number of times this document has been retried';
COMMENT ON COLUMN failed_documents.error_type IS 'Type of error: parse_error, api_error, embedding_error, storage_error';
