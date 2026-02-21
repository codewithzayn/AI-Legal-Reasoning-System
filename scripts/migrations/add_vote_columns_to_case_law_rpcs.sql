-- =============================================================================
-- Add vote strength, judge metadata, and depth analysis to case law RPC return types.
-- Requires: add_vote_strength.sql, add_depth_analysis_columns.sql (case_law columns)
-- =============================================================================

-- 1. vector_search_case_law (drop both overloads: vector and vector(1536))
DROP FUNCTION IF EXISTS vector_search_case_law(vector(1536), float, int, text);
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
  similarity float,
  dissenting_opinion boolean,
  judges text,
  judges_total int,
  judges_dissenting int,
  vote_strength text,
  exceptions text,
  weighted_factors text,
  trend_direction text,
  distinctive_facts text,
  ruling_instruction text,
  applied_provisions text
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
    1 - (cs.embedding <=> query_embedding) AS similarity,
    COALESCE(cl.dissenting_opinion, false),
    cl.judges,
    COALESCE(cl.judges_total, 0),
    COALESCE(cl.judges_dissenting, 0),
    COALESCE(cl.vote_strength, ''),
    COALESCE(cl.exceptions, ''),
    COALESCE(cl.weighted_factors, ''),
    COALESCE(cl.trend_direction, ''),
    COALESCE(cl.distinctive_facts, ''),
    COALESCE(cl.ruling_instruction, ''),
    COALESCE(cl.applied_provisions, '')
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
  rank real,
  dissenting_opinion boolean,
  judges text,
  judges_total int,
  judges_dissenting int,
  vote_strength text,
  exceptions text,
  weighted_factors text,
  trend_direction text,
  distinctive_facts text,
  ruling_instruction text,
  applied_provisions text
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
    ts_rank(cs.fts_vector, websearch_to_tsquery('finnish', query_text)) AS rank,
    COALESCE(cl.dissenting_opinion, false),
    cl.judges,
    COALESCE(cl.judges_total, 0),
    COALESCE(cl.judges_dissenting, 0),
    COALESCE(cl.vote_strength, ''),
    COALESCE(cl.exceptions, ''),
    COALESCE(cl.weighted_factors, ''),
    COALESCE(cl.trend_direction, ''),
    COALESCE(cl.distinctive_facts, ''),
    COALESCE(cl.ruling_instruction, ''),
    COALESCE(cl.applied_provisions, '')
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
  rank real,
  dissenting_opinion boolean,
  judges text,
  judges_total int,
  judges_dissenting int,
  vote_strength text,
  exceptions text,
  weighted_factors text,
  trend_direction text,
  distinctive_facts text,
  ruling_instruction text,
  applied_provisions text
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
    ts_rank(cs.fts_vector, to_tsquery('finnish', query_text)) AS rank,
    COALESCE(cl.dissenting_opinion, false),
    cl.judges,
    COALESCE(cl.judges_total, 0),
    COALESCE(cl.judges_dissenting, 0),
    COALESCE(cl.vote_strength, ''),
    COALESCE(cl.exceptions, ''),
    COALESCE(cl.weighted_factors, ''),
    COALESCE(cl.trend_direction, ''),
    COALESCE(cl.distinctive_facts, ''),
    COALESCE(cl.ruling_instruction, ''),
    COALESCE(cl.applied_provisions, '')
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
  meta_score real,
  dissenting_opinion boolean,
  judges text,
  judges_total int,
  judges_dissenting int,
  vote_strength text,
  exceptions text,
  weighted_factors text,
  trend_direction text,
  distinctive_facts text,
  ruling_instruction text,
  applied_provisions text
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
      ts_rank(cl.metadata_fts, websearch_to_tsquery('finnish', query_text)) AS meta_score,
      COALESCE(cl.dissenting_opinion, false),
      cl.judges,
      COALESCE(cl.judges_total, 0),
      COALESCE(cl.judges_dissenting, 0),
      COALESCE(cl.vote_strength, ''),
      COALESCE(cl.exceptions, ''),
      COALESCE(cl.weighted_factors, ''),
      COALESCE(cl.trend_direction, ''),
      COALESCE(cl.distinctive_facts, ''),
      COALESCE(cl.ruling_instruction, ''),
      COALESCE(cl.applied_provisions, '')
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

COMMENT ON FUNCTION vector_search_case_law(vector(1536), float, int, text) IS 'ANN vector search on case_law_sections; returns vote_strength and judge counts for legal analysis';
COMMENT ON FUNCTION fts_search_case_law(text, int, text) IS 'Full-text search on case_law_sections; returns vote_strength and judge counts for legal analysis';
COMMENT ON FUNCTION prefix_fts_search_case_law(text, int, text) IS 'Prefix FTS on case_law_sections; returns vote_strength and judge counts for legal analysis';
COMMENT ON FUNCTION search_case_law_metadata(text, int, text) IS 'FTS on case_law metadata; returns vote_strength and judge counts for legal analysis';
