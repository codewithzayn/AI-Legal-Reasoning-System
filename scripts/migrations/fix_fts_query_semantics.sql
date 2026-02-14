-- ============================================
-- FIX: FTS Query Semantics — plainto_tsquery → websearch_to_tsquery
-- ============================================
-- Problem:
--   plainto_tsquery('finnish', 'word1 word2 word3') produces:
--     'word1' & 'word2' & 'word3'    (AND — ALL must match)
--   For typical legal questions with 5-10 terms, this returns 0 results
--   because no single section contains ALL terms.
--
-- Solution:
--   websearch_to_tsquery('finnish', 'word1 OR word2 OR word3') produces:
--     'word1' | 'word2' | 'word3'    (OR — ANY can match)
--   ts_rank still scores higher when MORE terms match, preserving precision.
--   Plain space-separated input (no OR) still works as AND, so this is
--   fully backward-compatible.
--
-- Verified:
--   - "vahingonkorvauslain OR oikeuspaikka OR tahdonvaltainen"
--     returns KKO:1987:135 (the correct case) as a top result.
--   - The old query with all terms AND'd returned 0 results.
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
        ts_rank(s.fts_vector, websearch_to_tsquery('finnish', query_text))::float8 AS rank
    FROM case_law_sections s
    JOIN case_law c ON s.case_law_id = c.id
    WHERE s.fts_vector @@ websearch_to_tsquery('finnish', query_text)
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
            websearch_to_tsquery('finnish', query_text)
        )::float8 AS meta_score
    FROM case_law c
    JOIN case_law_sections s ON s.case_law_id = c.id
    WHERE
        case_law_metadata_tsvector(
            c.case_id, c.title, c.judgment, c.background_summary, c.decision_outcome,
            c.legal_domains, c.cited_cases, c.cited_laws, c.cited_eu_cases, c.cited_regulations
        ) @@ websearch_to_tsquery('finnish', query_text)
    ORDER BY meta_score DESC
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;


-- ============================================
-- COMMENTS
-- ============================================
COMMENT ON FUNCTION fts_search_case_law IS 'Full-text search on case_law_sections using GIN index (websearch_to_tsquery for OR support)';
COMMENT ON FUNCTION search_case_law_metadata IS 'Full-text search on case_law metadata columns (websearch_to_tsquery for OR support)';
