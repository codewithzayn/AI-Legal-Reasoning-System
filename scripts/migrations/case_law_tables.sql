-- ============================================
-- COMPREHENSIVE FINNISH CASE LAW SCHEMA
-- Supports: KKO, KHO, Courts of Appeal, Administrative Courts,
-- Special Courts (Market, Labour, Insurance), Case Law in Literature
-- ============================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================
-- 1. CASE_LAW TABLE (Universal Parent - All Courts)
-- ============================================
CREATE TABLE IF NOT EXISTS case_law (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- === CORE IDENTIFIERS ===
    case_id TEXT UNIQUE NOT NULL,           -- 'KKO:2026:7', 'KHO 16.1.2026/97', 'TT 2019:125', 'MAO:751/2025'
    court_type TEXT NOT NULL,               -- 'supreme_court', 'supreme_administrative_court', 'court_of_appeal', 'administrative_court', 'market_court', 'labour_court', 'insurance_court', 'case_law_literature'
    court_code TEXT,                        -- 'KKO', 'KHO', 'MAO', 'TT', 'VakO', 'HelHO'
    
    -- === DECISION TYPE ===
    decision_type TEXT NOT NULL,            -- 'precedent', 'other_decision', 'leave_to_appeal', 'brief_explanation', 'ruling', 'decision', 'commentary'
    
    -- === DATES ===
    case_year INTEGER NOT NULL,
    decision_date DATE,
    
    -- === OFFICIAL IDENTIFIERS ===
    diary_number TEXT,                      -- 'R2024/345', '2957/2024', 'R 24/18', '4444:2016'
    volume INTEGER,                         -- Volume number (if applicable)
    ecli TEXT,                              -- 'ECLI:FI:KKO:2026:7', 'ECLI:FI:KHO:2026:T97' (null for many)
    
    -- === CASE NUMBERS (Court-specific) ===
    case_number TEXT,                       -- General case number

    ruling_number TEXT,                     -- '1660' (Court of Appeal)
    
    -- === CONTENT ===
    title TEXT,                             -- Case title
    full_text TEXT,                         -- Complete decision text
    
    -- === LEGAL REFERENCES ===
    legal_domains TEXT[],                   -- ['Criminal Law', 'Sentencing']
    cited_laws TEXT[],                      -- ['Criminal Code Chapter 6 Section 13']
    cited_cases TEXT[],                     -- Referenced precedents
    cited_government_proposals TEXT[],      -- ['HE 44/2002 vp']
    cited_eu_cases TEXT[],                  -- ['C-185/89 Velker']
    cited_regulations TEXT[],               -- ['Council Regulation (EU) No 833/2014']

    
    -- === PARTIES (for applicable courts) ===
    applicant TEXT,                         -- Market Court, Labour Court
    defendant TEXT,                         -- Market Court, Labour Court
    respondent TEXT,
    
    -- === LOWER COURT INFORMATION ===
    lower_court_name TEXT,
    lower_court_date DATE,
    lower_court_number TEXT,
    lower_court_decision TEXT,              -- Brief description
    
    appeal_court_name TEXT,
    appeal_court_date DATE,
    appeal_court_number TEXT,
    
    -- === PROCEDURAL INFORMATION ===
    background_summary TEXT,                -- Background of the matter
    complaint TEXT,                         -- Complainant's demands
    answer TEXT,                            -- Defendant's response
    
    -- === DECISION INFORMATION ===
    decision_outcome TEXT,                  -- 'appeal_accepted', 'appeal_dismissed', 'partially_accepted'
    judgment TEXT,                          -- Final judgment/ruling
    dissenting_opinion BOOLEAN DEFAULT FALSE,
    dissenting_text TEXT,                   -- Dissenting opinion content
    judges TEXT,                            -- Comma-separated list of judges

    
    -- === COST ALLOCATION ===
    costs_awarded BOOLEAN DEFAULT FALSE,
    cost_amount DECIMAL(10,2),
    cost_recipient TEXT,
    
    -- === APPEAL INFORMATION ===
    appeal_instructions TEXT,               -- How to appeal
    is_final BOOLEAN,                       -- Is decision final/binding
    can_be_appealed BOOLEAN,
    appeal_deadline_days INTEGER,
    
    -- === LANGUAGE ===
    primary_language TEXT DEFAULT 'finnish',
    available_languages TEXT[],
    
    -- === SOURCE ===
    url TEXT,
    
    -- === ADDITIONAL METADATA ===
    is_published BOOLEAN DEFAULT TRUE,
    is_precedent BOOLEAN DEFAULT FALSE,     -- True for official precedents
    legal_significance TEXT,                -- 'high', 'medium', 'low'
    
    -- === COMMENTARY (for Case Law in Literature) ===
    related_case_id TEXT,                   -- Links to the actual case being commented on
    
    -- === TIMESTAMPS ===
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- === CONSTRAINTS ===
    CONSTRAINT valid_court_type CHECK (court_type IN (
        'supreme_court', 'supreme_administrative_court', 'court_of_appeal', 
        'administrative_court', 'market_court', 'labour_court', 
        'insurance_court', 'case_law_literature'
    )),
    CONSTRAINT valid_decision_type CHECK (decision_type IN (
        'precedent', 'other_decision', 'other_published_decision', 'leave_to_appeal', 
        'brief_explanation', 'ruling', 'decision', 'commentary', 'judgment'
    ))
);

-- === INDEXES FOR case_law ===
CREATE INDEX IF NOT EXISTS idx_case_law_court_type ON case_law(court_type);
CREATE INDEX IF NOT EXISTS idx_case_law_court_code ON case_law(court_code);
CREATE INDEX IF NOT EXISTS idx_case_law_decision_type ON case_law(decision_type);
CREATE INDEX IF NOT EXISTS idx_case_law_year ON case_law(case_year);
CREATE INDEX IF NOT EXISTS idx_case_law_case_id ON case_law(case_id);
CREATE INDEX IF NOT EXISTS idx_case_law_ecli ON case_law(ecli) WHERE ecli IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_case_law_decision_date ON case_law(decision_date);
CREATE INDEX IF NOT EXISTS idx_case_law_legal_domains ON case_law USING GIN(legal_domains);
CREATE INDEX IF NOT EXISTS idx_case_law_cited_laws ON case_law USING GIN(cited_laws);
CREATE INDEX IF NOT EXISTS idx_case_law_cited_regulations ON case_law USING GIN(cited_regulations);
CREATE INDEX IF NOT EXISTS idx_case_law_is_precedent ON case_law(is_precedent);

-- Full-text search
CREATE INDEX IF NOT EXISTS idx_case_law_title_fts ON case_law USING GIN(to_tsvector('finnish', COALESCE(title, '')));


-- ============================================
-- 2. CASE_LAW_SECTIONS TABLE (Chunked Content)
-- ============================================
CREATE TABLE IF NOT EXISTS case_law_sections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    case_law_id UUID NOT NULL REFERENCES case_law(id) ON DELETE CASCADE,
    
    -- Section metadata
    section_type TEXT NOT NULL,             
    section_number INTEGER,
    section_title TEXT,
    section_subtitle TEXT,
    
    -- Content
    content TEXT NOT NULL,
    content_length INTEGER,
    
    -- Importance for semantic search
    embedding_priority TEXT DEFAULT 'medium',
    
    -- Search vectors
    embedding VECTOR(1536),
    fts_vector TSVECTOR,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT valid_section_type CHECK (section_type IN (
        'background', 'facts', 'lower_court', 'appeal_court', 'legal_question',
        'applicable_provisions', 'reasoning', 'decision', 'verdict', 'judgment',
        'judges', 'dissenting_opinion', 'complaint', 'answer', 'counter_explanation',
        'cost_allocation', 'appeal_instructions', 'summary', 'commentary', 'other'
    )),
    CONSTRAINT valid_priority CHECK (embedding_priority IN ('high', 'medium', 'low'))
);

CREATE INDEX IF NOT EXISTS idx_case_law_sections_case_law_id ON case_law_sections(case_law_id);
CREATE INDEX IF NOT EXISTS idx_case_law_sections_type ON case_law_sections(section_type);
CREATE INDEX IF NOT EXISTS idx_case_law_sections_priority ON case_law_sections(embedding_priority);
CREATE INDEX IF NOT EXISTS idx_case_law_sections_embedding ON case_law_sections USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_case_law_sections_fts ON case_law_sections USING GIN(fts_vector);


-- ============================================
-- 3. CASE_LAW_REFERENCES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS case_law_references (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    source_case_id UUID NOT NULL REFERENCES case_law(id) ON DELETE CASCADE,
    
    referenced_id TEXT NOT NULL,
    reference_type TEXT NOT NULL,
    reference_description TEXT,
    referenced_in_section_id UUID REFERENCES case_law_sections(id) ON DELETE SET NULL,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(source_case_id, referenced_id, reference_type),
    
    CONSTRAINT valid_reference_type CHECK (reference_type IN (
        'case_law', 'legislation', 'government_proposal', 'eu_case', 
        'treaty', 'regulation', 'directive', 'collective_agreement', 'other'
    ))
);

CREATE INDEX IF NOT EXISTS idx_case_law_references_source ON case_law_references(source_case_id);
CREATE INDEX IF NOT EXISTS idx_case_law_references_referenced ON case_law_references(referenced_id);
CREATE INDEX IF NOT EXISTS idx_case_law_references_type ON case_law_references(reference_type);



-- ============================================
-- 4. FTS TRIGGER (Auto-update tsvector)
-- ============================================
CREATE OR REPLACE FUNCTION update_case_law_sections_fts()
RETURNS TRIGGER AS $$
BEGIN
    NEW.fts_vector := to_tsvector('finnish', COALESCE(NEW.content, ''));
    NEW.content_length := LENGTH(NEW.content);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_case_law_sections_fts ON case_law_sections;
CREATE TRIGGER trigger_case_law_sections_fts
    BEFORE INSERT OR UPDATE ON case_law_sections
    FOR EACH ROW
    EXECUTE FUNCTION update_case_law_sections_fts();


-- ============================================
-- 5. UPDATED_AT TRIGGER
-- ============================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_case_law_updated_at ON case_law;
CREATE TRIGGER trigger_case_law_updated_at
    BEFORE UPDATE ON case_law
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- ============================================
-- 6. ENHANCED SEARCH FUNCTION
-- ============================================
CREATE OR REPLACE FUNCTION search_case_law(
    query_embedding VECTOR(1536),
    query_text TEXT,
    match_count INT DEFAULT 10,
    court_type_filter TEXT DEFAULT NULL,
    court_code_filter TEXT DEFAULT NULL,
    decision_type_filter TEXT DEFAULT NULL,
    min_year INT DEFAULT NULL,
    max_year INT DEFAULT NULL,
    legal_domain_filter TEXT DEFAULT NULL,
    precedents_only BOOLEAN DEFAULT FALSE
)
RETURNS TABLE (
    section_id UUID,
    case_id TEXT,
    court_type TEXT,
    court_code TEXT,
    decision_type TEXT,
    case_year INTEGER,
    decision_date DATE,
    section_type TEXT,
    content TEXT,
    title TEXT,
    legal_domains TEXT[],
    ecli TEXT,
    url TEXT,
    vector_score FLOAT,
    fts_score FLOAT,
    combined_score FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.id AS section_id,
        c.case_id,
        c.court_type,
        c.court_code,
        c.decision_type,
        c.case_year,
        c.decision_date,
        s.section_type,
        s.content,
        c.title,
        c.legal_domains,
        c.ecli,
        c.url,
        (1 - (s.embedding <=> query_embedding))::float8 AS vector_score,
        ts_rank(s.fts_vector, plainto_tsquery('finnish', query_text))::float8 AS fts_score,
        (
            CASE 
                WHEN s.embedding_priority = 'high' THEN 0.75
                WHEN s.embedding_priority = 'medium' THEN 0.7
                ELSE 0.65
            END * (1 - (s.embedding <=> query_embedding))
        ) + 
        (0.3 * ts_rank(s.fts_vector, plainto_tsquery('finnish', query_text))::float8) AS combined_score
    FROM case_law_sections s
    JOIN case_law c ON s.case_law_id = c.id
    WHERE 
        (court_type_filter IS NULL OR c.court_type = court_type_filter) AND
        (court_code_filter IS NULL OR c.court_code = court_code_filter) AND
        (decision_type_filter IS NULL OR c.decision_type = decision_type_filter) AND
        (min_year IS NULL OR c.case_year >= min_year) AND
        (max_year IS NULL OR c.case_year <= max_year) AND
        (legal_domain_filter IS NULL OR legal_domain_filter = ANY(c.legal_domains)) AND
        (NOT precedents_only OR c.is_precedent = TRUE)
    ORDER BY combined_score DESC
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;


-- ============================================
-- 7. SEARCH BY COURT TYPE
-- ============================================
CREATE OR REPLACE FUNCTION search_by_court_type(
    court_type_param TEXT,
    year_param INT DEFAULT NULL,
    match_count INT DEFAULT 20
)
RETURNS TABLE (
    case_id TEXT,
    court_type TEXT,
    court_code TEXT,
    decision_type TEXT,
    case_year INTEGER,
    title TEXT,
    decision_date DATE,
    ecli TEXT,
    url TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.case_id,
        c.court_type,
        c.court_code,
        c.decision_type,
        c.case_year,
        c.title,
        c.decision_date,
        c.ecli,
        c.url
    FROM case_law c
    WHERE c.court_type = court_type_param
      AND (year_param IS NULL OR c.case_year = year_param)
    ORDER BY c.decision_date DESC
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;


-- ============================================
-- 8. FIND RELATED CASES
-- ============================================
CREATE OR REPLACE FUNCTION find_related_cases(
    source_case_id_param TEXT,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    case_id TEXT,
    court_type TEXT,
    case_year INTEGER,
    title TEXT,
    decision_date DATE,
    relationship TEXT,
    ecli TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT
        c.case_id,
        c.court_type,
        c.case_year,
        c.title,
        c.decision_date,
        'cited'::TEXT AS relationship,
        c.ecli
    FROM case_law c
    JOIN case_law source ON source.case_id = source_case_id_param
    WHERE 
        source_case_id_param = ANY(c.cited_cases) OR
        c.case_id = ANY(source.cited_cases)
    ORDER BY c.decision_date DESC
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;


-- ============================================
-- 9. INGESTION TRACKING
-- ============================================
CREATE TABLE IF NOT EXISTS case_law_ingestion_tracking (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    court_type TEXT NOT NULL,
    court_code TEXT,
    decision_type TEXT NOT NULL,
    year INTEGER NOT NULL,
    
    status TEXT DEFAULT 'pending',
    total_cases INTEGER DEFAULT 0,
    processed_cases INTEGER DEFAULT 0,
    failed_cases INTEGER DEFAULT 0,
    last_processed_case TEXT,
    error_message TEXT,
    
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(court_type, decision_type, year),
    
    CONSTRAINT valid_tracking_status CHECK (status IN ('pending', 'in_progress', 'completed', 'failed', 'partial'))
);

CREATE INDEX IF NOT EXISTS idx_tracking_court_type_year ON case_law_ingestion_tracking(court_type, year);
CREATE INDEX IF NOT EXISTS idx_tracking_status ON case_law_ingestion_tracking(status);


-- ============================================
-- 10. INGESTION ERRORS LOG
-- ============================================
CREATE TABLE IF NOT EXISTS case_law_ingestion_errors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    tracking_id UUID REFERENCES case_law_ingestion_tracking(id) ON DELETE CASCADE,
    case_id TEXT,
    url TEXT,
    error_type TEXT,
    error_message TEXT,
    error_details JSONB,
    
    occurred_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_errors_tracking_id ON case_law_ingestion_errors(tracking_id);
CREATE INDEX IF NOT EXISTS idx_errors_type ON case_law_ingestion_errors(error_type);


-- ============================================
-- 11. HELPFUL VIEWS
-- ============================================

-- Recent precedents across all courts
CREATE OR REPLACE VIEW recent_precedents AS
SELECT 
    case_id,
    court_type,
    court_code,
    case_year,
    decision_date,
    title,
    legal_domains,
    ecli,
    url
FROM case_law
WHERE is_precedent = TRUE
ORDER BY decision_date DESC
LIMIT 100;

-- Ingestion progress summary
CREATE OR REPLACE VIEW ingestion_progress_summary AS
SELECT 
    court_type,
    decision_type,
    year,
    status,
    total_cases,
    processed_cases,
    failed_cases,
    ROUND((processed_cases::DECIMAL / NULLIF(total_cases, 0)) * 100, 2) AS completion_percentage,
    last_updated
FROM case_law_ingestion_tracking
ORDER BY year DESC, court_type, decision_type;

-- Statistics by court
CREATE OR REPLACE VIEW court_statistics AS
SELECT 
    court_type,
    court_code,
    decision_type,
    COUNT(*) AS total_cases,
    MIN(case_year) AS earliest_year,
    MAX(case_year) AS latest_year,
    COUNT(*) FILTER (WHERE is_precedent = TRUE) AS precedent_count
FROM case_law
GROUP BY court_type, court_code, decision_type
ORDER BY court_type, decision_type;


-- ============================================
-- 12. UTILITY FUNCTIONS
-- ============================================

-- Get statistics
CREATE OR REPLACE FUNCTION get_case_statistics()
RETURNS TABLE (
    court_type TEXT,
    court_code TEXT,
    decision_type TEXT,
    total_cases BIGINT,
    earliest_year INTEGER,
    latest_year INTEGER,
    precedent_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.court_type,
        c.court_code,
        c.decision_type,
        COUNT(*) AS total_cases,
        MIN(c.case_year) AS earliest_year,
        MAX(c.case_year) AS latest_year,
        COUNT(*) FILTER (WHERE c.is_precedent = TRUE) AS precedent_count
    FROM case_law c
    GROUP BY c.court_type, c.court_code, c.decision_type
    ORDER BY c.court_type, c.decision_type;
END;
$$ LANGUAGE plpgsql;


-- COMMENTS FOR DOCUMENTATION
COMMENT ON TABLE case_law IS 'Universal table for all Finnish court case law: Supreme Court, Supreme Administrative Court, Courts of Appeal, Administrative Courts, Special Courts (Market, Labour, Insurance), and Case Law in Literature';
COMMENT ON TABLE case_law_sections IS 'Chunked sections of case law documents for semantic search';
COMMENT ON TABLE case_law_references IS 'Legal references cited in decisions';

COMMENT ON TABLE case_law_ingestion_tracking IS 'Tracks progress of case law scraping';
COMMENT ON TABLE case_law_ingestion_errors IS 'Logs ingestion errors';