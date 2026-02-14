-- ============================================
-- FIX: Enable prefix matching in FTS — to_tsquery replaces websearch_to_tsquery
-- ============================================
-- Problem:
--   websearch_to_tsquery does NOT support the :* (prefix match) operator.
--   Finnish compound words like "oikeuspaikkasäännös" never match the
--   base form "oikeuspaikka" in the tsvector because the Finnish stemmer
--   treats them as entirely different lexemes.
--
-- Solution:
--   Switch to to_tsquery which supports :* prefix matching.
--   The Python query builder (_build_fts_query) now generates
--   to_tsquery-compatible strings with | (OR) and :* operators:
--
--     to_tsquery('finnish',
--       'vahingonkorvauslain | vahingonkorv:* | vahingonkorvaus:*
--        | oikeuspaikkasäännös | oikeuspaik:* | oikeuspaikka:*
--        | pakottava | tahdonvaltainen | tahdonv:* | tahdonval:*')
--
--   This is GENERIC — no hardcoded Finnish suffixes.  For any word > 10
--   characters, shorter prefix variants are generated at multiple
--   truncation points (50%, 65%, 80% of word length).  At least one
--   truncation typically lands on a natural compound-word boundary.
--
-- Backward-compatible:
--   to_tsquery still accepts simple terms (e.g. 'word1 | word2')
--   and the Python side controls the query format.
--
-- RUN THIS IN SUPABASE SQL EDITOR.
-- ============================================


-- ============================================
-- 1. Update fts_search_case_law
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
        ts_rank(s.fts_vector, to_tsquery('finnish', query_text))::float8 AS rank
    FROM case_law_sections s
    JOIN case_law c ON s.case_law_id = c.id
    WHERE s.fts_vector @@ to_tsquery('finnish', query_text)
    ORDER BY rank DESC
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;


-- ============================================
-- 2. Update search_case_law_metadata
-- ============================================
CREATE OR REPLACE FUNCTION search_case_law_metadata(
    query_text TEXT,
    match_count INT DEFAULT 10
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
    meta_score FLOAT
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
        ts_rank(
            case_law_metadata_tsvector(
                c.case_id, c.title, c.judgment, c.background_summary, c.decision_outcome,
                c.legal_domains, c.cited_cases, c.cited_laws, c.cited_eu_cases, c.cited_regulations
            ),
            to_tsquery('finnish', query_text)
        )::float8 AS meta_score
    FROM case_law c
    JOIN case_law_sections s ON s.case_law_id = c.id
    WHERE
        case_law_metadata_tsvector(
            c.case_id, c.title, c.judgment, c.background_summary, c.decision_outcome,
            c.legal_domains, c.cited_cases, c.cited_laws, c.cited_eu_cases, c.cited_regulations
        ) @@ to_tsquery('finnish', query_text)
    ORDER BY meta_score DESC
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;


-- ============================================
-- COMMENTS
-- ============================================
COMMENT ON FUNCTION fts_search_case_law IS 'Full-text search on case_law_sections using GIN index (to_tsquery for :* prefix matching)';
COMMENT ON FUNCTION search_case_law_metadata IS 'Full-text search on case_law metadata columns (to_tsquery for :* prefix matching)';
