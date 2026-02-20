-- =============================================================================
-- Fix RPC return types: bigint → uuid for section_id and id columns
-- The original add_multi_tenant.sql incorrectly declared these as bigint,
-- but case_law_sections.id and legal_chunks.id are UUID.
-- Must DROP first because Postgres cannot change return types via REPLACE.
-- =============================================================================

-- 1. vector_search_case_law
DROP FUNCTION IF EXISTS vector_search_case_law(vector, float, int, text);
CREATE FUNCTION vector_search_case_law(
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

-- 2. fts_search_case_law
DROP FUNCTION IF EXISTS fts_search_case_law(text, int, text);
CREATE FUNCTION fts_search_case_law(
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

-- 3. prefix_fts_search_case_law
DROP FUNCTION IF EXISTS prefix_fts_search_case_law(text, int, text);
CREATE FUNCTION prefix_fts_search_case_law(
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

-- 4. search_case_law_metadata
DROP FUNCTION IF EXISTS search_case_law_metadata(text, int, text);
CREATE FUNCTION search_case_law_metadata(
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

-- 5. vector_search (legal_chunks)
DROP FUNCTION IF EXISTS vector_search(vector, float, int, text);
CREATE FUNCTION vector_search(
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

-- 6. fts_search (legal_chunks)
DROP FUNCTION IF EXISTS fts_search(text, int, text);
CREATE FUNCTION fts_search(
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
