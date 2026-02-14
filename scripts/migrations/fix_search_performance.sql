-- ============================================
-- FIX: Search Performance for case_law_sections
-- ============================================
-- Problem: The existing search_case_law() RPC computes cosine distance
-- for ALL 67K+ rows and sorts by a combined score, which prevents
-- PostgreSQL from using the HNSW index. This causes 60s+ timeouts.
--
-- Solution: Two separate RPCs that each use their own index:
--   1. vector_search_case_law  → uses HNSW index (fast ANN)
--   2. fts_search_case_law     → uses GIN index (fast text search)
-- Python-side RRF merge combines the results.
--
-- RUN THIS IN SUPABASE SQL EDITOR.
-- ============================================


-- Step 0: Ensure the HNSW index exists (idempotent)
CREATE INDEX IF NOT EXISTS idx_case_law_sections_embedding
    ON case_law_sections USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Ensure GIN index for FTS exists (idempotent)
CREATE INDEX IF NOT EXISTS idx_case_law_sections_fts
    ON case_law_sections USING GIN(fts_vector);


-- ============================================
-- 1. VECTOR SEARCH on case_law_sections (HNSW-indexed)
-- ============================================
-- This function uses ORDER BY embedding <=> query_embedding LIMIT N
-- which allows PostgreSQL to use the HNSW index for fast ANN search.
-- ============================================
CREATE OR REPLACE FUNCTION vector_search_case_law(
    query_embedding VECTOR(1536),
    match_threshold FLOAT DEFAULT 0.3,
    match_count INT DEFAULT 20
)
RETURNS TABLE (
    section_id UUID,
    case_id TEXT,
    court_type TEXT,
    case_year INTEGER,
    section_type TEXT,
    content TEXT,
    title TEXT,
    legal_domains TEXT[],
    ecli TEXT,
    url TEXT,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        s.id AS section_id,
        c.case_id,
        c.court_type,
        c.case_year,
        s.section_type,
        s.content,
        c.title,
        c.legal_domains,
        c.ecli,
        c.url,
        (1 - (s.embedding <=> query_embedding))::float8 AS similarity
    FROM case_law_sections s
    JOIN case_law c ON s.case_law_id = c.id
    WHERE 1 - (s.embedding <=> query_embedding) > match_threshold
    ORDER BY s.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;


-- ============================================
-- 2. FTS SEARCH on case_law_sections (GIN-indexed)
-- ============================================
-- Full-text search using Finnish stemmer + GIN index.
-- ============================================
CREATE OR REPLACE FUNCTION fts_search_case_law(
    query_text TEXT,
    match_count INT DEFAULT 20
)
RETURNS TABLE (
    section_id UUID,
    case_id TEXT,
    court_type TEXT,
    case_year INTEGER,
    section_type TEXT,
    content TEXT,
    title TEXT,
    legal_domains TEXT[],
    ecli TEXT,
    url TEXT,
    rank FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        s.id AS section_id,
        c.case_id,
        c.court_type,
        c.case_year,
        s.section_type,
        s.content,
        c.title,
        c.legal_domains,
        c.ecli,
        c.url,
        ts_rank(s.fts_vector, plainto_tsquery('finnish', query_text))::float8 AS rank
    FROM case_law_sections s
    JOIN case_law c ON s.case_law_id = c.id
    WHERE s.fts_vector @@ plainto_tsquery('finnish', query_text)
    ORDER BY rank DESC
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;


-- ============================================
-- COMMENTS
-- ============================================
COMMENT ON FUNCTION vector_search_case_law IS 'ANN vector search on case_law_sections using HNSW index';
COMMENT ON FUNCTION fts_search_case_law IS 'Full-text search on case_law_sections using GIN index';
