-- =============================================================================
-- Multi-Tenant Client Document Ingestion Migration
-- Adds tenant_id columns, client document tracking tables, and updates RPCs
-- for tenant-aware search with isolation.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Add tenant_id columns to existing tables
-- ---------------------------------------------------------------------------

ALTER TABLE case_law
  ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT NULL;

ALTER TABLE case_law_sections
  ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT NULL;

ALTER TABLE legal_chunks
  ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT NULL;

ALTER TABLE feedback
  ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT NULL;

ALTER TABLE conversations
  ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT NULL;

-- Indexes for tenant filtering
CREATE INDEX IF NOT EXISTS idx_case_law_tenant_id
  ON case_law (tenant_id) WHERE tenant_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_case_law_sections_tenant_id
  ON case_law_sections (tenant_id) WHERE tenant_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_legal_chunks_tenant_id
  ON legal_chunks (tenant_id) WHERE tenant_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_feedback_tenant_id
  ON feedback (tenant_id) WHERE tenant_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_conversations_tenant_id
  ON conversations (tenant_id) WHERE tenant_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 2. Relax CHECK constraints: add 'client_document' to enums
-- ---------------------------------------------------------------------------

-- Drop and recreate court_type CHECK to include 'client_document'
ALTER TABLE case_law DROP CONSTRAINT IF EXISTS valid_court_type;
ALTER TABLE case_law ADD CONSTRAINT valid_court_type CHECK (
  court_type IN (
    'supreme_court', 'supreme_administrative_court',
    'court_of_appeal', 'administrative_court',
    'district_court', 'special_court',
    'insurance_court', 'labour_court', 'market_court',
    'client_document'
  )
);

-- Drop and recreate decision_type CHECK to include 'client_document'
ALTER TABLE case_law DROP CONSTRAINT IF EXISTS valid_decision_type;
ALTER TABLE case_law ADD CONSTRAINT valid_decision_type CHECK (
  decision_type IS NULL OR decision_type IN (
    'precedent', 'ruling', 'order', 'decision',
    'annual_report', 'other',
    'client_document'
  )
);

-- ---------------------------------------------------------------------------
-- 3. Create client_documents tracking table
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS client_documents (
  id            BIGSERIAL PRIMARY KEY,
  tenant_id     TEXT NOT NULL,
  source_provider TEXT DEFAULT 'upload',  -- 'upload', 'google_drive', 'onedrive'
  source_file_id  TEXT,                   -- external file ID from drive
  file_name     TEXT NOT NULL,
  file_type     TEXT,                     -- 'pdf', 'docx', 'txt'
  status        TEXT DEFAULT 'pending',   -- 'pending', 'processing', 'completed', 'failed'
  content_hash  TEXT,                     -- SHA-256 for idempotency
  chunks_stored INTEGER DEFAULT 0,
  error_message TEXT,
  case_law_id   UUID REFERENCES case_law(id) ON DELETE SET NULL,
  created_at    TIMESTAMPTZ DEFAULT now(),
  updated_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_client_documents_tenant
  ON client_documents (tenant_id);
CREATE INDEX IF NOT EXISTS idx_client_documents_hash
  ON client_documents (tenant_id, content_hash);

-- ---------------------------------------------------------------------------
-- 4. Create tenant_drive_connections table
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tenant_drive_connections (
  id            BIGSERIAL PRIMARY KEY,
  tenant_id     TEXT NOT NULL,
  provider      TEXT NOT NULL,            -- 'google_drive', 'onedrive'
  access_token  TEXT,
  refresh_token TEXT,
  token_expiry  TIMESTAMPTZ,
  folder_id     TEXT,                     -- root folder to scan
  created_at    TIMESTAMPTZ DEFAULT now(),
  updated_at    TIMESTAMPTZ DEFAULT now(),
  UNIQUE (tenant_id, provider)
);

-- ---------------------------------------------------------------------------
-- 5. Update RPC functions with tenant_id parameter
-- ---------------------------------------------------------------------------

-- 5a. vector_search_case_law — add optional p_tenant_id
CREATE OR REPLACE FUNCTION vector_search_case_law(
  query_embedding vector(1536),
  match_threshold float DEFAULT 0.3,
  match_count int DEFAULT 25,
  p_tenant_id text DEFAULT NULL
)
RETURNS TABLE (
  section_id uuid,
  case_id text,
  title text,
  court_type text,
  case_year int,
  section_type text,
  content text,
  legal_domains text[],
  url text,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    cs.id AS section_id,
    cl.case_id,
    cl.title,
    cl.court_type,
    cl.case_year,
    cs.section_type,
    cs.content,
    cl.legal_domains,
    cl.url,
    1 - (cs.embedding <=> query_embedding) AS similarity
  FROM case_law_sections cs
  JOIN case_law cl ON cl.id = cs.case_law_id
  WHERE cs.embedding IS NOT NULL
    AND 1 - (cs.embedding <=> query_embedding) > match_threshold
    AND (cl.tenant_id IS NULL OR cl.tenant_id = p_tenant_id)
    AND (cs.tenant_id IS NULL OR cs.tenant_id = p_tenant_id)
  ORDER BY cs.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- 5b. fts_search_case_law — add optional p_tenant_id
CREATE OR REPLACE FUNCTION fts_search_case_law(
  query_text text,
  match_count int DEFAULT 25,
  p_tenant_id text DEFAULT NULL
)
RETURNS TABLE (
  section_id uuid,
  case_id text,
  title text,
  court_type text,
  case_year int,
  section_type text,
  content text,
  legal_domains text[],
  url text,
  rank real
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    cs.id AS section_id,
    cl.case_id,
    cl.title,
    cl.court_type,
    cl.case_year,
    cs.section_type,
    cs.content,
    cl.legal_domains,
    cl.url,
    ts_rank(cs.fts_vector, websearch_to_tsquery('finnish', query_text)) AS rank
  FROM case_law_sections cs
  JOIN case_law cl ON cl.id = cs.case_law_id
  WHERE cs.fts_vector @@ websearch_to_tsquery('finnish', query_text)
    AND (cl.tenant_id IS NULL OR cl.tenant_id = p_tenant_id)
    AND (cs.tenant_id IS NULL OR cs.tenant_id = p_tenant_id)
  ORDER BY rank DESC
  LIMIT match_count;
END;
$$;

-- 5c. prefix_fts_search_case_law — add optional p_tenant_id
CREATE OR REPLACE FUNCTION prefix_fts_search_case_law(
  query_text text,
  match_count int DEFAULT 25,
  p_tenant_id text DEFAULT NULL
)
RETURNS TABLE (
  section_id uuid,
  case_id text,
  title text,
  court_type text,
  case_year int,
  section_type text,
  content text,
  legal_domains text[],
  url text,
  rank real
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    cs.id AS section_id,
    cl.case_id,
    cl.title,
    cl.court_type,
    cl.case_year,
    cs.section_type,
    cs.content,
    cl.legal_domains,
    cl.url,
    ts_rank(cs.fts_vector, to_tsquery('finnish', query_text)) AS rank
  FROM case_law_sections cs
  JOIN case_law cl ON cl.id = cs.case_law_id
  WHERE cs.fts_vector @@ to_tsquery('finnish', query_text)
    AND (cl.tenant_id IS NULL OR cl.tenant_id = p_tenant_id)
    AND (cs.tenant_id IS NULL OR cs.tenant_id = p_tenant_id)
  ORDER BY rank DESC
  LIMIT match_count;
END;
$$;

-- 5d. search_case_law_metadata — add optional p_tenant_id
CREATE OR REPLACE FUNCTION search_case_law_metadata(
  query_text text,
  match_count int DEFAULT 10,
  p_tenant_id text DEFAULT NULL
)
RETURNS TABLE (
  section_id uuid,
  case_id text,
  title text,
  court_type text,
  case_year int,
  section_type text,
  content text,
  legal_domains text[],
  decision_outcome text,
  url text,
  meta_score real
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT * FROM (
    SELECT DISTINCT ON (cl.case_id)
      cs.id AS section_id,
      cl.case_id,
      cl.title,
      cl.court_type,
      cl.case_year,
      cs.section_type,
      cs.content,
      cl.legal_domains,
      cl.decision_outcome,
      cl.url,
      ts_rank(cl.metadata_fts, websearch_to_tsquery('finnish', query_text)) AS meta_score
    FROM case_law cl
    JOIN case_law_sections cs ON cs.case_law_id = cl.id
    WHERE cl.metadata_fts @@ websearch_to_tsquery('finnish', query_text)
      AND (cl.tenant_id IS NULL OR cl.tenant_id = p_tenant_id)
      AND (cs.tenant_id IS NULL OR cs.tenant_id = p_tenant_id)
    ORDER BY cl.case_id, meta_score DESC
  ) sub
  ORDER BY meta_score DESC
  LIMIT match_count;
END;
$$;

-- 5e. vector_search (legal_chunks) — add optional p_tenant_id
CREATE OR REPLACE FUNCTION vector_search(
  query_embedding vector(1536),
  match_threshold float DEFAULT 0.5,
  match_count int DEFAULT 10,
  p_tenant_id text DEFAULT NULL
)
RETURNS TABLE (
  id uuid,
  document_title text,
  document_uri text,
  chunk_text text,
  chunk_index int,
  section_number text,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    lc.id,
    lc.document_title,
    lc.document_uri,
    lc.chunk_text,
    lc.chunk_index,
    lc.section_number,
    1 - (lc.embedding <=> query_embedding) AS similarity
  FROM legal_chunks lc
  WHERE lc.embedding IS NOT NULL
    AND 1 - (lc.embedding <=> query_embedding) > match_threshold
    AND (lc.tenant_id IS NULL OR lc.tenant_id = p_tenant_id)
  ORDER BY lc.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- 5f. fts_search (legal_chunks) — add optional p_tenant_id
CREATE OR REPLACE FUNCTION fts_search(
  query_text text,
  match_count int DEFAULT 10,
  p_tenant_id text DEFAULT NULL
)
RETURNS TABLE (
  id uuid,
  document_title text,
  document_uri text,
  chunk_text text,
  chunk_index int,
  section_number text,
  rank real
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    lc.id,
    lc.document_title,
    lc.document_uri,
    lc.chunk_text,
    lc.chunk_index,
    lc.section_number,
    ts_rank(lc.fts_vector, websearch_to_tsquery('finnish', query_text)) AS rank
  FROM legal_chunks lc
  WHERE lc.fts_vector @@ websearch_to_tsquery('finnish', query_text)
    AND (lc.tenant_id IS NULL OR lc.tenant_id = p_tenant_id)
  ORDER BY rank DESC
  LIMIT match_count;
END;
$$;
