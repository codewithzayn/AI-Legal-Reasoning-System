-- ============================================
-- ADD: prefix_fts_search_case_law RPC
-- ============================================
-- Enables prefix matching (:*) on case_law_sections.fts_vector.
-- Used by the _prefix_content_search Python channel to match
-- Finnish compound words across word boundaries.
--
-- Example: to_tsquery('finnish', 'osamaksu:*') matches
--   "osamaksukauppa", "osamaksumyyjä", "osamaksusopimus" etc.
--
-- The GIN index idx_case_law_sections_fts supports prefix queries
-- efficiently, so no new index is needed.
--
-- RUN IN SUPABASE SQL EDITOR.
-- ============================================

CREATE OR REPLACE FUNCTION prefix_fts_search_case_law(
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
        ts_rank(s.fts_vector, to_tsquery('finnish', query_text))::float8 AS rank
    FROM case_law_sections s
    JOIN case_law c ON s.case_law_id = c.id
    WHERE s.fts_vector @@ to_tsquery('finnish', query_text)
    ORDER BY rank DESC
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION prefix_fts_search_case_law IS
    'Prefix FTS on case_law_sections using to_tsquery (supports :* prefix operator for compound words)';
