-- ============================================
-- FIX: Metadata Coverage + RPC Case-Level Dedup
-- ============================================
-- RUN EACH STEP SEPARATELY in Supabase SQL Editor.
-- Step B uses LIMIT 500 batches. Run repeatedly until 0 rows updated.
-- ============================================


-- ============================================
-- STEP A: Fix RPCs (run once)
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
    SELECT DISTINCT ON (tc.case_id)
        s.id AS section_id,
        tc.case_id,
        tc.court_type,
        tc.court_code,
        tc.decision_type,
        tc.case_year,
        tc.decision_date,
        s.section_type,
        s.content,
        tc.title,
        tc.legal_domains,
        tc.ecli,
        tc.url,
        tc.meta_score
    FROM (
        SELECT
            c.id, c.case_id, c.court_type, c.court_code, c.decision_type,
            c.case_year, c.decision_date, c.title, c.legal_domains, c.ecli, c.url,
            ts_rank(
                case_law_metadata_tsvector(
                    c.case_id, c.title, c.judgment, c.background_summary, c.decision_outcome,
                    c.legal_domains, c.cited_cases, c.cited_laws, c.cited_eu_cases, c.cited_regulations
                ),
                websearch_to_tsquery('finnish', query_text)
            )::float8 AS meta_score
        FROM case_law c
        WHERE
            case_law_metadata_tsvector(
                c.case_id, c.title, c.judgment, c.background_summary, c.decision_outcome,
                c.legal_domains, c.cited_cases, c.cited_laws, c.cited_eu_cases, c.cited_regulations
            ) @@ websearch_to_tsquery('finnish', query_text)
        ORDER BY meta_score DESC
        LIMIT match_count
    ) tc
    JOIN case_law_sections s ON s.case_law_id = tc.id
    ORDER BY tc.case_id, s.id;
END;
$$ LANGUAGE plpgsql;

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
-- STEP B1: Backfill background_summary (mixed-case headers)
-- Run repeatedly until 0 rows updated.
-- ============================================
UPDATE case_law c
SET background_summary = LEFT(
    SUBSTRING(
        c.full_text
        FROM CASE
            WHEN c.full_text LIKE '%Asian tausta ja kysymyksenasettelu%'
            THEN POSITION('Asian tausta ja kysymyksenasettelu' IN c.full_text) + 34
            WHEN c.full_text LIKE '%Asian tausta%'
            THEN POSITION('Asian tausta' IN c.full_text) + 12
            ELSE POSITION('Asian k' IN c.full_text) + 37
        END
        FOR 2000
    ),
    2000
)
WHERE (c.background_summary IS NULL OR c.background_summary = '')
  AND (c.full_text LIKE '%Asian tausta%' OR c.full_text LIKE '%Asian k%sittely alemmissa%')
  AND c.id IN (
      SELECT id FROM case_law
      WHERE (background_summary IS NULL OR background_summary = '')
        AND (full_text LIKE '%Asian tausta%' OR full_text LIKE '%Asian k%sittely alemmissa%')
      LIMIT 500
  );


-- ============================================
-- STEP B2: Backfill background_summary (all remaining cases)
-- Fallback: extract chars 200-2200 from full_text.
-- Run repeatedly until 0 rows updated.
-- ============================================
UPDATE case_law c
SET background_summary = LEFT(SUBSTRING(c.full_text FROM 200 FOR 2000), 2000)
WHERE (c.background_summary IS NULL OR c.background_summary = '')
  AND c.full_text IS NOT NULL
  AND LENGTH(c.full_text) > 200
  AND c.id IN (
      SELECT id FROM case_law
      WHERE (background_summary IS NULL OR background_summary = '')
        AND full_text IS NOT NULL AND LENGTH(full_text) > 200
      LIMIT 500
  );


-- ============================================
-- STEP C: Fix legal_domains (run once)
-- ============================================
UPDATE case_law
SET legal_domains = string_to_array(legal_domains[1], ', ')
WHERE array_length(legal_domains, 1) = 1
  AND legal_domains[1] LIKE '%,%';


-- ============================================
-- STEP D: Fix English cited_laws (run once)
-- ============================================
UPDATE case_law c
SET cited_laws = sub.laws
FROM (
    SELECT
        cl.id,
        ARRAY(
            SELECT DISTINCT TRIM(m[1])
            FROM regexp_matches(
                SUBSTRING(cl.full_text FROM 1 FOR LEAST(
                    COALESCE(NULLIF(POSITION('Asian k' IN cl.full_text), 0), 2000),
                    2000
                )),
                '(?:^|\n)\s*([A-Z][A-Za-z\-]*L?\s+\d[^\n]*[^\n]*)',
                'g'
            ) AS m
        ) AS laws
    FROM case_law cl
    WHERE cl.cited_laws[1] LIKE 'Chapter%'
) sub
WHERE c.id = sub.id
  AND array_length(sub.laws, 1) > 0;


-- ============================================
-- STEP E: Rebuild metadata FTS index (run once after all backfills)
-- ============================================
REINDEX INDEX idx_case_law_metadata_fts;


-- ============================================
-- STEP F: Verify
-- ============================================
SELECT case_id, title,
    LENGTH(COALESCE(background_summary, '')) AS bg_len,
    legal_domains, cited_laws
FROM case_law WHERE case_id = 'KKO:1998:162';

SELECT
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE background_summary IS NOT NULL AND background_summary != '') AS has_bg,
    COUNT(*) FILTER (WHERE legal_domains IS NOT NULL AND legal_domains != '{}') AS has_domains
FROM case_law;

SELECT case_id, meta_score
FROM search_case_law_metadata('huumausainerikos', 50)
WHERE case_id = 'KKO:1998:162';
