-- Supabase Database Schema for Finnish Legal AI System
-- Hybrid Search: pgvector (semantic) + Full-Text Search (BM25-like) but right now ts_rank for MVP

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Main Table: legal_chunks
-- Stores chunked legal documents with embeddings and metadata

CREATE TABLE IF NOT EXISTS legal_chunks (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Document identification (for citations)
    document_uri TEXT NOT NULL,              -- Finlex URI (e.g., "https://finlex.fi/fi/laki/ajantasa/2025/20250001")
    document_title TEXT NOT NULL,            -- Document title (e.g., "Rahoituslaki")
    document_year INTEGER NOT NULL,          -- Year of document (e.g., 2025)
    document_type TEXT,                      -- Type: "statute" etc.
    document_category TEXT,                 -- Type: "act", etc.
    
    -- Chunk content
    chunk_text TEXT NOT NULL,                -- Actual text content of the chunk
    chunk_index INTEGER NOT NULL,            -- Order of chunk in document (0, 1, 2...)
    section_number TEXT,                     -- Legal section reference (e.g., "§ 3", "§ 15")
    
    -- Search vectors
    embedding VECTOR(1536),                  -- OpenAI text-embedding-3-small (1536 dimensions)
    fts TSVECTOR,                           -- Full-text search vector (auto-generated)
    
    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,      -- Additional context (e.g., {"chapter": "2", "subsection": "a"})
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT legal_chunks_uri_chunk_unique UNIQUE (document_uri, chunk_index)
);

-- Indexes for Performance

-- 1. Vector similarity search (HNSW index for fast approximate nearest neighbor)
CREATE INDEX IF NOT EXISTS legal_chunks_embedding_idx 
ON legal_chunks 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- 2. Full-text search index (GIN for fast text search)
CREATE INDEX IF NOT EXISTS legal_chunks_fts_idx 
ON legal_chunks 
USING GIN (fts);

-- 3. Document URI index (for fast citation lookups)
CREATE INDEX IF NOT EXISTS legal_chunks_uri_idx 
ON legal_chunks (document_uri);

-- 4. Year index (for filtering by time period)
CREATE INDEX IF NOT EXISTS legal_chunks_year_idx 
ON legal_chunks (document_year);

-- 5. Composite index for document + chunk ordering
CREATE INDEX IF NOT EXISTS legal_chunks_doc_chunk_idx 
ON legal_chunks (document_uri, chunk_index);

-- Triggers: Auto-update FTS vector and timestamp

-- Function to auto-generate FTS vector from chunk_text
CREATE OR REPLACE FUNCTION update_fts_vector()
RETURNS TRIGGER AS $$
BEGIN
    -- Use Finnish language configuration for better stemming
    NEW.fts := to_tsvector('finnish', COALESCE(NEW.chunk_text, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update FTS on insert/update
DROP TRIGGER IF EXISTS legal_chunks_fts_trigger ON legal_chunks;
CREATE TRIGGER legal_chunks_fts_trigger
BEFORE INSERT OR UPDATE OF chunk_text
ON legal_chunks
FOR EACH ROW
EXECUTE FUNCTION update_fts_vector();

-- Function to auto-update timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update timestamp
DROP TRIGGER IF EXISTS legal_chunks_updated_at_trigger ON legal_chunks;
CREATE TRIGGER legal_chunks_updated_at_trigger
BEFORE UPDATE ON legal_chunks
FOR EACH ROW
EXECUTE FUNCTION update_updated_at();

-- Helper Functions for Hybrid Search

-- Function: Vector similarity search
CREATE OR REPLACE FUNCTION vector_search(
    query_embedding VECTOR(1536),
    match_threshold FLOAT DEFAULT 0.5,
    match_count INT DEFAULT 50
)
RETURNS TABLE (
    id UUID,
    document_uri TEXT,
    document_title TEXT,
    section_number TEXT,
    chunk_text TEXT,
    similarity FLOAT,
    metadata JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        lc.id,
        lc.document_uri,
        lc.document_title,
        lc.section_number,
        lc.chunk_text,
        1 - (lc.embedding <=> query_embedding) AS similarity,
        lc.metadata
    FROM legal_chunks lc
    WHERE 1 - (lc.embedding <=> query_embedding) > match_threshold
    ORDER BY lc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- Function: Full-text search with BM25-like ranking
CREATE OR REPLACE FUNCTION fts_search(
    query_text TEXT,
    match_count INT DEFAULT 50
)
RETURNS TABLE (
    id UUID,
    document_uri TEXT,
    document_title TEXT,
    section_number TEXT,
    chunk_text TEXT,
    rank REAL,
    metadata JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        lc.id,
        lc.document_uri,
        lc.document_title,
        lc.section_number,
        lc.chunk_text,
        ts_rank_cd(lc.fts, query) AS rank,
        lc.metadata
    FROM legal_chunks lc,
         to_tsquery('finnish', query_text) query
    WHERE lc.fts @@ query
    ORDER BY ts_rank_cd(lc.fts, query) DESC
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- Row Level Security (RLS) - Optional but recommended

-- Enable RLS
ALTER TABLE legal_chunks ENABLE ROW LEVEL SECURITY;

-- Policy: Allow public read access (adjust based on your needs)
CREATE POLICY "Allow public read access"
ON legal_chunks
FOR SELECT
TO public
USING (true);

-- Policy: Restrict insert/update/delete to authenticated users
CREATE POLICY "Allow authenticated insert"
ON legal_chunks
FOR INSERT
TO authenticated
WITH CHECK (true);

CREATE POLICY "Allow authenticated update"
ON legal_chunks
FOR UPDATE
TO authenticated
USING (true);

CREATE POLICY "Allow authenticated delete"
ON legal_chunks
FOR DELETE
TO authenticated
USING (true);

-- ============================================================================
-- Sample Query Examples (for testing)
-- ============================================================================

-- Example 1: Vector search
-- SELECT * FROM vector_search(
--     '[0.1, 0.2, ...]'::vector(1536),  -- Your query embedding
--     0.5,                               -- Similarity threshold
--     10                                 -- Top 10 results
-- );

-- Example 2: Full-text search
-- SELECT * FROM fts_search(
--     'työnantajan & velvollisuudet',   -- Query (use & for AND, | for OR)
--     10                                 -- Top 10 results
-- );

-- Example 3: Get all chunks for a specific document
-- SELECT * FROM legal_chunks 
-- WHERE document_uri = 'https://finlex.fi/fi/laki/ajantasa/2025/20250001'
-- ORDER BY chunk_index;

-- Statistics and Monitoring

-- View: Document statistics
CREATE OR REPLACE VIEW document_stats AS
SELECT 
    document_uri,
    document_title,
    document_year,
    COUNT(*) as chunk_count,
    MIN(created_at) as first_indexed,
    MAX(updated_at) as last_updated
FROM legal_chunks
GROUP BY document_uri, document_title, document_year
ORDER BY document_year DESC, document_title;

-- ============================================================================
-- Cleanup and Maintenance
-- ============================================================================

-- Function to remove duplicate chunks (if needed)
CREATE OR REPLACE FUNCTION remove_duplicate_chunks()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    WITH duplicates AS (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY document_uri, chunk_index 
                   ORDER BY created_at DESC
               ) as rn
        FROM legal_chunks
    )
    DELETE FROM legal_chunks
    WHERE id IN (SELECT id FROM duplicates WHERE rn > 1);
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Setup Complete!
-- ============================================================================

-- Verify setup
DO $$
BEGIN
    RAISE NOTICE 'Database schema setup complete!';
    RAISE NOTICE 'Table: legal_chunks created';
    RAISE NOTICE 'Indexes: 5 indexes created (vector, fts, uri, year, composite)';
    RAISE NOTICE 'Functions: vector_search, fts_search, and helpers created';
    RAISE NOTICE 'Ready for document ingestion!';
END $$;
