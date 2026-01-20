-- Ingestion Tracking Table
-- Tracks progress of document ingestion by category/type/year

CREATE TABLE IF NOT EXISTS ingestion_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Document classification
    document_category TEXT NOT NULL,        -- e.g., "act", "judgment", "doc"
    document_type TEXT NOT NULL,            -- e.g., "statute", "government-proposal"
    year INTEGER NOT NULL,                  -- e.g., 2025, 2024
    
    -- Progress tracking
    last_processed_page INTEGER DEFAULT 0,  -- Last page number processed
    documents_processed INTEGER DEFAULT 0,  -- Documents successfully processed
    documents_failed INTEGER DEFAULT 0,     -- Documents that failed processing
    
    -- Status
    status TEXT DEFAULT 'pending',          -- pending, in_progress, completed, no_documents, failed
    error_message TEXT,                     -- Last error if failed
    
    -- Timestamps
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT ingestion_tracking_unique UNIQUE (document_category, document_type, year)
);

-- Index for querying tracking status
CREATE INDEX IF NOT EXISTS ingestion_tracking_status_idx 
ON ingestion_tracking (document_category, document_type, year, status);
