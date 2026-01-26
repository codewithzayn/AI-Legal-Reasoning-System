-- ============================================
-- Case Law Tables Migration
-- Supreme Court (KKO) and Supreme Administrative Court (KHO)
-- ============================================

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- 1. CASE_LAW TABLE (Parent - Metadata)
-- ============================================
CREATE TABLE IF NOT EXISTS case_law (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Case identifiers
    case_id TEXT UNIQUE NOT NULL,           -- 'KKO:2026:5' or 'KHO:2025:88'
    court TEXT NOT NULL,                     -- 'kko' or 'kho'
    year INTEGER NOT NULL,
    case_number INTEGER,                     -- e.g., 5 from KKO:2026:5
    
    -- Dates
    decision_date DATE,
    
    -- Official identifiers
    diary_number TEXT,                       -- Diaarinumero: 'R2024/604'

    ecli TEXT,                               -- 'ECLI:FI:KKO:2026:5'
    
    -- Content
    full_text TEXT,                          -- Complete document for backup
    
    -- Metadata
    keywords TEXT[],                         -- Asiasanat: ['Sotilasrikos', 'Palvelusrikos']
    language TEXT DEFAULT 'fin',             -- Language code
    url TEXT,                                -- Source URL
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for case_law
CREATE INDEX IF NOT EXISTS idx_case_law_court ON case_law(court);
CREATE INDEX IF NOT EXISTS idx_case_law_year ON case_law(year);
CREATE INDEX IF NOT EXISTS idx_case_law_case_id ON case_law(case_id);
CREATE INDEX IF NOT EXISTS idx_case_law_ecli ON case_law(ecli);
CREATE INDEX IF NOT EXISTS idx_case_law_keywords ON case_law USING GIN(keywords);


-- ============================================
-- 2. CASE_LAW_SECTIONS TABLE (Child - Chunks)
-- ============================================
CREATE TABLE IF NOT EXISTS case_law_sections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Parent reference
    case_law_id UUID NOT NULL REFERENCES case_law(id) ON DELETE CASCADE,
    
    -- Section info
    section_type TEXT NOT NULL,              -- 'summary', 'lower_court', 'appeal', 'reasoning', 'verdict', 'judges'
    section_number INTEGER,                  -- For ordering within document
    section_title TEXT,                      -- e.g., 'Korkeimman oikeuden ratkaisu'
    
    -- Content
    content TEXT NOT NULL,
    
    -- Search vectors
    embedding VECTOR(1536),                  -- OpenAI ada-002 embedding
    fts_vector TSVECTOR,                     -- Full-text search vector
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for case_law_sections
CREATE INDEX IF NOT EXISTS idx_case_law_sections_case_law_id ON case_law_sections(case_law_id);
CREATE INDEX IF NOT EXISTS idx_case_law_sections_type ON case_law_sections(section_type);
CREATE INDEX IF NOT EXISTS idx_case_law_sections_embedding ON case_law_sections USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_case_law_sections_fts ON case_law_sections USING GIN(fts_vector);


-- ============================================
-- 3. CASE_LAW_REFERENCES TABLE (Related Cases)
-- ============================================
CREATE TABLE IF NOT EXISTS case_law_references (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Source case
    source_case_id UUID NOT NULL REFERENCES case_law(id) ON DELETE CASCADE,
    
    -- Referenced case/law
    referenced_id TEXT NOT NULL,             -- 'KKO:2025:58' or 'Rikoslain 45 luvun 1 §'
    reference_type TEXT NOT NULL,            -- 'precedent', 'legislation', 'government_proposal'
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Prevent duplicates
    UNIQUE(source_case_id, referenced_id)
);

-- Index for references
CREATE INDEX IF NOT EXISTS idx_case_law_references_source ON case_law_references(source_case_id);
CREATE INDEX IF NOT EXISTS idx_case_law_references_referenced ON case_law_references(referenced_id);


-- ============================================
-- 4. FTS TRIGGER (Auto-update tsvector)
-- ============================================
CREATE OR REPLACE FUNCTION update_case_law_sections_fts()
RETURNS TRIGGER AS $$
BEGIN
    NEW.fts_vector := to_tsvector('finnish', COALESCE(NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_case_law_sections_fts ON case_law_sections;
CREATE TRIGGER trigger_case_law_sections_fts
    BEFORE INSERT OR UPDATE ON case_law_sections
    FOR EACH ROW
    EXECUTE FUNCTION update_case_law_sections_fts();


-- ============================================
-- 5. SEARCH FUNCTION (Hybrid: Vector + FTS)
-- ============================================
CREATE OR REPLACE FUNCTION search_case_law(
    query_embedding VECTOR(1536),
    query_text TEXT,
    match_count INT DEFAULT 10,
    court_filter TEXT DEFAULT NULL,
    year_filter INT DEFAULT NULL
)
RETURNS TABLE (
    section_id UUID,
    case_id TEXT,
    court TEXT,
    year INTEGER,
    section_type TEXT,
    content TEXT,
    keywords TEXT[],
    vector_score FLOAT,
    fts_score FLOAT,
    combined_score FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.id AS section_id,
        c.case_id,
        c.court,
        c.year,
        s.section_type,
        s.content,
        c.keywords,
        1 - (s.embedding <=> query_embedding) AS vector_score,
        ts_rank(s.fts_vector, plainto_tsquery('finnish', query_text))::float8 AS fts_score,
        (0.7 * (1 - (s.embedding <=> query_embedding))) + 
        (0.3 * ts_rank(s.fts_vector, plainto_tsquery('finnish', query_text))::float8) AS combined_score
    FROM case_law_sections s
    JOIN case_law c ON s.case_law_id = c.id
    WHERE 
        (court_filter IS NULL OR c.court = court_filter) AND
        (year_filter IS NULL OR c.year = year_filter)
    ORDER BY combined_score DESC
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;


-- ============================================
-- 6. INGESTION TRACKING FOR CASE LAW
-- ============================================
CREATE TABLE IF NOT EXISTS case_law_ingestion_tracking (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    court TEXT NOT NULL,                     -- 'kko' or 'kho'
    year INTEGER NOT NULL,
    status TEXT DEFAULT 'pending',           -- 'pending', 'in_progress', 'completed', 'failed'
    total_cases INTEGER DEFAULT 0,
    processed_cases INTEGER DEFAULT 0,
    failed_cases INTEGER DEFAULT 0,
    last_processed_case TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(court, year)
);

CREATE INDEX IF NOT EXISTS idx_case_law_tracking_court_year ON case_law_ingestion_tracking(court, year);
