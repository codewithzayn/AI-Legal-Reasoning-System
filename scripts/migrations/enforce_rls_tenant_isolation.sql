-- =============================================================================
-- Migration: Enforce Row-Level Security for multi-tenant isolation
--
-- Problem: client_documents table had no RLS; any anon-key caller could read
-- all tenants' private documents. case_law rows with a non-null tenant_id
-- (client documents stored there) were also accessible to any tenant.
--
-- Fix:
--   1. Enable RLS on client_documents with strict per-user policies.
--   2. Enable RLS on tenant_drive_connections.
--   3. Add a stricter SQL helper that enforces client-document rows are ONLY
--      returned to the exact owning tenant (no NULL-fallback).
--   4. Recreate the vector/FTS RPCs with the stricter client-doc check.
--
-- NOTE: Backend uses the service role key, which bypasses RLS automatically.
--       RLS here protects the anon/authenticated key paths (e.g. direct API
--       calls from the browser or third-party integrations).
--
-- Run ONCE against your Supabase project:
--   psql $DATABASE_URL -f scripts/migrations/enforce_rls_tenant_isolation.sql
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. RLS on client_documents
-- ---------------------------------------------------------------------------

ALTER TABLE client_documents ENABLE ROW LEVEL SECURITY;

-- Authenticated users can only access their own documents
CREATE POLICY client_documents_select_own ON client_documents
  FOR SELECT USING (tenant_id = auth.uid()::text);

CREATE POLICY client_documents_insert_own ON client_documents
  FOR INSERT WITH CHECK (tenant_id = auth.uid()::text);

CREATE POLICY client_documents_update_own ON client_documents
  FOR UPDATE USING (tenant_id = auth.uid()::text)
  WITH CHECK (tenant_id = auth.uid()::text);

CREATE POLICY client_documents_delete_own ON client_documents
  FOR DELETE USING (tenant_id = auth.uid()::text);

-- ---------------------------------------------------------------------------
-- 2. RLS on tenant_drive_connections
-- ---------------------------------------------------------------------------

ALTER TABLE tenant_drive_connections ENABLE ROW LEVEL SECURITY;

CREATE POLICY drive_connections_select_own ON tenant_drive_connections
  FOR SELECT USING (tenant_id = auth.uid()::text);

CREATE POLICY drive_connections_insert_own ON tenant_drive_connections
  FOR INSERT WITH CHECK (tenant_id = auth.uid()::text);

CREATE POLICY drive_connections_update_own ON tenant_drive_connections
  FOR UPDATE USING (tenant_id = auth.uid()::text)
  WITH CHECK (tenant_id = auth.uid()::text);

CREATE POLICY drive_connections_delete_own ON tenant_drive_connections
  FOR DELETE USING (tenant_id = auth.uid()::text);

-- ---------------------------------------------------------------------------
-- 3. Helper: strict tenant filter for case_law sections
--    Returns true when a row is accessible to p_tenant:
--      - Shared content (tenant_id IS NULL) → always visible
--      - Client-document row (tenant_id IS NOT NULL) → only to exact owner
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION is_accessible_to_tenant(
  row_tenant_id text,
  p_tenant_id   text
) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
  SELECT row_tenant_id IS NULL
      OR (p_tenant_id IS NOT NULL AND row_tenant_id = p_tenant_id)
$$;

-- ---------------------------------------------------------------------------
-- 4. Recreate RPCs with strict tenant isolation
--    (replaces the add_multi_tenant.sql versions that used the weaker
--     NULL-OR-match filter on both cl and cs independently)
-- ---------------------------------------------------------------------------

-- Drop existing functions first so PostgreSQL allows return-type changes.
-- (CREATE OR REPLACE fails when the return column list differs from the stored version.)
DROP FUNCTION IF EXISTS vector_search_case_law(vector, float, int, text);
DROP FUNCTION IF EXISTS fts_search_case_law(text, int, text);
DROP FUNCTION IF EXISTS prefix_fts_search_case_law(text, int, text);
DROP FUNCTION IF EXISTS search_case_law_metadata(text, int, text);
DROP FUNCTION IF EXISTS vector_search(vector, float, int, text);
DROP FUNCTION IF EXISTS fts_search(text, int, text);

-- 4a. vector_search_case_law
CREATE OR REPLACE FUNCTION vector_search_case_law(
  query_embedding vector(1536),
  match_threshold float DEFAULT 0.3,
  match_count     int   DEFAULT 25,
  p_tenant_id     text  DEFAULT NULL
)
RETURNS TABLE (
  section_id    uuid,
  case_id       text,
  title         text,
  court_type    text,
  case_year     int,
  section_type  text,
  content       text,
  legal_domains text[],
  url           text,
  similarity    float
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
    -- Strict: client-document rows only visible to their owning tenant
    AND is_accessible_to_tenant(cl.tenant_id, p_tenant_id)
    AND is_accessible_to_tenant(cs.tenant_id, p_tenant_id)
  ORDER BY cs.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- 4b. fts_search_case_law
CREATE OR REPLACE FUNCTION fts_search_case_law(
  query_text  text,
  match_count int  DEFAULT 25,
  p_tenant_id text DEFAULT NULL
)
RETURNS TABLE (
  section_id    uuid,
  case_id       text,
  title         text,
  court_type    text,
  case_year     int,
  section_type  text,
  content       text,
  legal_domains text[],
  url           text,
  rank          real
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
    AND is_accessible_to_tenant(cl.tenant_id, p_tenant_id)
    AND is_accessible_to_tenant(cs.tenant_id, p_tenant_id)
  ORDER BY rank DESC
  LIMIT match_count;
END;
$$;

-- 4c. prefix_fts_search_case_law
CREATE OR REPLACE FUNCTION prefix_fts_search_case_law(
  query_text  text,
  match_count int  DEFAULT 25,
  p_tenant_id text DEFAULT NULL
)
RETURNS TABLE (
  section_id    uuid,
  case_id       text,
  title         text,
  court_type    text,
  case_year     int,
  section_type  text,
  content       text,
  legal_domains text[],
  url           text,
  rank          real
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
    AND is_accessible_to_tenant(cl.tenant_id, p_tenant_id)
    AND is_accessible_to_tenant(cs.tenant_id, p_tenant_id)
  ORDER BY rank DESC
  LIMIT match_count;
END;
$$;

-- 4d. search_case_law_metadata
CREATE OR REPLACE FUNCTION search_case_law_metadata(
  query_text  text,
  match_count int  DEFAULT 10,
  p_tenant_id text DEFAULT NULL
)
RETURNS TABLE (
  section_id      uuid,
  case_id         text,
  title           text,
  court_type      text,
  case_year       int,
  section_type    text,
  content         text,
  legal_domains   text[],
  decision_outcome text,
  url             text,
  meta_score      real
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
      AND is_accessible_to_tenant(cl.tenant_id, p_tenant_id)
      AND is_accessible_to_tenant(cs.tenant_id, p_tenant_id)
    ORDER BY cl.case_id, meta_score DESC
  ) sub
  ORDER BY meta_score DESC
  LIMIT match_count;
END;
$$;

-- 4e. vector_search (legal_chunks)
CREATE OR REPLACE FUNCTION vector_search(
  query_embedding vector(1536),
  match_threshold float DEFAULT 0.5,
  match_count     int   DEFAULT 10,
  p_tenant_id     text  DEFAULT NULL
)
RETURNS TABLE (
  id             uuid,
  document_title text,
  document_uri   text,
  chunk_text     text,
  chunk_index    int,
  section_number text,
  similarity     float
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
    AND is_accessible_to_tenant(lc.tenant_id, p_tenant_id)
  ORDER BY lc.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- 4f. fts_search (legal_chunks)
CREATE OR REPLACE FUNCTION fts_search(
  query_text  text,
  match_count int  DEFAULT 10,
  p_tenant_id text DEFAULT NULL
)
RETURNS TABLE (
  id             uuid,
  document_title text,
  document_uri   text,
  chunk_text     text,
  chunk_index    int,
  section_number text,
  rank           real
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
    AND is_accessible_to_tenant(lc.tenant_id, p_tenant_id)
  ORDER BY rank DESC
  LIMIT match_count;
END;
$$;

-- ---------------------------------------------------------------------------
-- 5. Verify: check RLS is enabled (informational, run manually)
-- ---------------------------------------------------------------------------
-- SELECT tablename, rowsecurity FROM pg_tables
-- WHERE schemaname = 'public'
--   AND tablename IN ('client_documents', 'tenant_drive_connections');