-- =============================================================================
-- AI Legal Reasoning System – Supabase Maintenance Queries
-- =============================================================================
-- Use these in the Supabase SQL Editor (Dashboard → SQL Editor → New Query)
-- Always preview with SELECT before running DELETE/UPDATE.
-- =============================================================================


-- =============================================
-- 1. SCHEMA SETUP (run once)
-- =============================================

-- Add content_hash column for idempotency (skip re-processing unchanged docs)
ALTER TABLE case_law ADD COLUMN IF NOT EXISTS content_hash TEXT;

-- Increase statement timeout (default ~8s is too short for vector search with many chunks)
-- Safe for production: only limits how long a single query can run.
ALTER ROLE authenticator SET statement_timeout = '60s';


-- =============================================
-- 1b. METADATA FTS INDEX + FUNCTION
-- =============================================
-- NOTE: case_law_metadata_tsvector(), GIN index, and search_case_law_metadata()
-- are defined in the canonical migration: scripts/migrations/case_law_tables.sql
-- Run that migration first; do NOT duplicate them here.


-- =============================================
-- 2. VIEW / INSPECT
-- =============================================

-- Count all documents by court and year
SELECT court_type, case_year, COUNT(*) AS total
FROM case_law
GROUP BY court_type, case_year
ORDER BY court_type, case_year DESC;

-- View all documents for a specific year and court
SELECT case_id, decision_date, ecli, diary_number, content_hash
FROM case_law
WHERE court_type = 'supreme_court' AND case_year = 2026
ORDER BY case_id;

-- -----------------------------------------------------------------------------
-- Check whether data for a year is present in Supabase (use for 2026, 2025, … any year)
-- Replace 2026 with the year you want to check.
-- -----------------------------------------------------------------------------
-- Count by court and type for that year
SELECT court_type, decision_type, case_year, COUNT(*) AS documents_in_supabase
FROM case_law
WHERE case_year = 2026
GROUP BY court_type, decision_type, case_year
ORDER BY court_type, decision_type;

-- List all case_id for that year (to compare with JSON or ingestion tracking)
SELECT case_id, court_type, decision_type, case_year
FROM case_law
WHERE case_year = 2026
ORDER BY case_id;

-- -----------------------------------------------------------------------------
-- Last year that was ingested (run the ingestion pipeline) – from actual data
-- Use this to know where you left off before running ingest-history again.
-- -----------------------------------------------------------------------------
SELECT MAX(case_year) AS last_year_ingested
FROM case_law;

-- Same idea from ingestion tracking (latest year with a tracking row)
-- SELECT MAX(year) AS last_year_in_tracking FROM case_law_ingestion_tracking;

-- -----------------------------------------------------------------------------
-- Ingestion status: per year, how many total / processed / failed / remaining
-- (Matches ingestion_manager: total=expected, processed=in Supabase, failed=this run, remaining=total−processed)
-- -----------------------------------------------------------------------------
SELECT
    court_type,
    decision_type,
    year,
    status,
    total_cases AS total,
    processed_cases AS processed,
    failed_cases AS failed,
    GREATEST(0, total_cases - processed_cases) AS remaining,
    last_processed_case,
    completed_at
FROM case_law_ingestion_tracking
ORDER BY year DESC, court_type, decision_type;

-- Same but for one specific year (replace 1983 with your year)
-- SELECT court_type, decision_type, year, status, total_cases, processed_cases, failed_cases,
--        GREATEST(0, total_cases - processed_cases) AS remaining, completed_at
-- FROM case_law_ingestion_tracking
-- WHERE year = 1983
-- ORDER BY court_type, decision_type;

-- Validate: compare tracking.processed_cases to actual count in case_law (should match)
SELECT
    t.court_type,
    t.decision_type,
    t.year,
    t.status,
    t.total_cases,
    t.processed_cases AS tracking_processed,
    COUNT(c.id) AS actual_in_case_law,
    t.processed_cases - COUNT(c.id) AS diff
FROM case_law_ingestion_tracking t
LEFT JOIN case_law c ON c.court_type = t.court_type AND c.decision_type = t.decision_type AND c.case_year = t.year
GROUP BY t.court_type, t.decision_type, t.year, t.status, t.total_cases, t.processed_cases
ORDER BY t.year DESC, t.court_type, t.decision_type;

-- View ingestion errors (failed documents)
SELECT e.case_id, e.error_type, e.error_message, e.url, e.occurred_at, t.year, t.court_type
FROM case_law_ingestion_errors e
JOIN case_law_ingestion_tracking t ON e.tracking_id = t.id
ORDER BY e.occurred_at DESC;

-- Find documents with missing metadata (NULL fields that should be populated)
SELECT case_id, decision_date, ecli, diary_number, volume, judges
FROM case_law
WHERE court_type = 'supreme_court'
  AND case_year = 2026
  AND (ecli IS NULL OR decision_date IS NULL OR diary_number IS NULL)
ORDER BY case_id;


-- =============================================
-- 3. DELETE & RE-PROCESS (by year + court)
-- =============================================
-- Use these to wipe a specific year so the ingestion pipeline re-processes everything.
-- Run in order: sections → references → errors → case_law → tracking.

-- Step 1: Preview what will be deleted
SELECT case_id FROM case_law
WHERE court_type = 'supreme_court' AND case_year = 2026;


-- Step 2: Delete sections (child rows first — they reference case_law.id)
DELETE FROM case_law_sections
WHERE case_law_id IN (
    SELECT id FROM case_law
    WHERE court_type = 'supreme_court' AND case_year = 2026
);

-- Step 3: Delete references
DELETE FROM case_law_references
WHERE source_case_id IN (
    SELECT id FROM case_law
    WHERE court_type = 'supreme_court' AND case_year = 2026
);

-- Step 4: Delete ingestion errors for that year
DELETE FROM case_law_ingestion_errors
WHERE tracking_id IN (
    SELECT id FROM case_law_ingestion_tracking
    WHERE court_type = 'supreme_court' AND year = 2026
);

-- Step 5: Delete the case_law records themselves
DELETE FROM case_law
WHERE court_type = 'supreme_court' AND case_year = 2026;

-- Step 6: Reset tracking status
DELETE FROM case_law_ingestion_tracking
WHERE court_type = 'supreme_court' AND year = 2026;

-- After running all steps above, re-run:
--   make ingest-precedents YEAR=2026


-- =============================================
-- 4. DELETE A SINGLE DOCUMENT (by case_id)
-- =============================================

-- Preview
SELECT id, case_id, case_year FROM case_law WHERE case_id = 'KKO:2025:5';

-- Delete sections
DELETE FROM case_law_sections
WHERE case_law_id = (SELECT id FROM case_law WHERE case_id = 'KKO:2025:5');

-- Delete references
DELETE FROM case_law_references
WHERE source_case_id = (SELECT id FROM case_law WHERE case_id = 'KKO:2025:5');

-- Delete the document
DELETE FROM case_law WHERE case_id = 'KKO:2025:5';

-- After this, re-run:
--   make ingest-precedents YEAR=2025
-- Only this document will be re-processed (others skipped via content_hash).


-- =============================================
-- 5. DELETE BY DECISION TYPE (e.g. only precedents for a year)
-- =============================================

-- Preview
SELECT case_id FROM case_law
WHERE court_type = 'supreme_court' AND case_year = 2026 AND decision_type = 'precedent';

-- Delete sections
DELETE FROM case_law_sections
WHERE case_law_id IN (
    SELECT id FROM case_law
    WHERE court_type = 'supreme_court' AND case_year = 2026 AND decision_type = 'precedent'
);

-- Delete references
DELETE FROM case_law_references
WHERE source_case_id IN (
    SELECT id FROM case_law
    WHERE court_type = 'supreme_court' AND case_year = 2026 AND decision_type = 'precedent'
);

-- Delete documents
DELETE FROM case_law
WHERE court_type = 'supreme_court' AND case_year = 2026 AND decision_type = 'precedent';


-- =============================================
-- 6. DELETE ALL DATA FOR A YEAR RANGE (e.g. 1958–2000 or 2020–2026)
-- =============================================
-- Deletes from all 5 tables: case_law_sections, case_law_references,
-- case_law_ingestion_errors, case_law, case_law_ingestion_tracking.
-- Replace 1958 and 2000 with your range. Run PREVIEW first.

-- ---------- PREVIEW: rows that will be removed (run first) ----------
SELECT 'case_law' AS tbl, COUNT(*) AS cnt FROM case_law WHERE case_year BETWEEN 1958 AND 2000
UNION ALL
SELECT 'case_law_sections', COUNT(*) FROM case_law_sections WHERE case_law_id IN (SELECT id FROM case_law WHERE case_year BETWEEN 1958 AND 2000)
UNION ALL
SELECT 'case_law_references', COUNT(*) FROM case_law_references WHERE source_case_id IN (SELECT id FROM case_law WHERE case_year BETWEEN 1958 AND 2000)
UNION ALL
SELECT 'case_law_ingestion_errors', COUNT(*) FROM case_law_ingestion_errors WHERE tracking_id IN (SELECT id FROM case_law_ingestion_tracking WHERE year BETWEEN 1958 AND 2000)
UNION ALL
SELECT 'case_law_ingestion_tracking', COUNT(*) FROM case_law_ingestion_tracking WHERE year BETWEEN 1958 AND 2000;

-- ---------- DELETE 1958–2000 (all courts/types). Run in order. ----------
-- Step 1: Sections (child of case_law)
DELETE FROM case_law_sections
WHERE case_law_id IN (SELECT id FROM case_law WHERE case_year BETWEEN 1958 AND 2000);

-- Step 2: References (child of case_law)
DELETE FROM case_law_references
WHERE source_case_id IN (SELECT id FROM case_law WHERE case_year BETWEEN 1958 AND 2000);

-- Step 3: Ingestion errors (by tracking year)
DELETE FROM case_law_ingestion_errors
WHERE tracking_id IN (SELECT id FROM case_law_ingestion_tracking WHERE year BETWEEN 1958 AND 2000);

-- Step 4: Documents
DELETE FROM case_law
WHERE case_year BETWEEN 1958 AND 2000;

-- Step 5: Tracking rows for that year range
DELETE FROM case_law_ingestion_tracking
WHERE year BETWEEN 1958 AND 2000;

-- After this, re-ingest the range (e.g. 2000 down to 1926):
--   make ingest-history START=1926 END=2000 COURT=supreme_court SUBTYPE=precedent
-- (Or only 1958–2000: START=1958 END=2000)


-- ---------- Same pattern for another range (e.g. 2020–2026, supreme_court precedent only) ----------
-- Step 1: Delete sections
DELETE FROM case_law_sections
WHERE case_law_id IN (
    SELECT id FROM case_law
    WHERE court_type = 'supreme_court' AND case_year BETWEEN 2020 AND 2026
);

-- Step 2: Delete references
DELETE FROM case_law_references
WHERE source_case_id IN (
    SELECT id FROM case_law
    WHERE court_type = 'supreme_court' AND case_year BETWEEN 2020 AND 2026
);

-- Step 3: Delete ingestion errors
DELETE FROM case_law_ingestion_errors
WHERE tracking_id IN (
    SELECT id FROM case_law_ingestion_tracking
    WHERE court_type = 'supreme_court' AND year BETWEEN 2020 AND 2026
);

-- Step 4: Delete the documents
DELETE FROM case_law
WHERE court_type = 'supreme_court' AND case_year BETWEEN 2020 AND 2026;

-- Step 5: Reset tracking
DELETE FROM case_law_ingestion_tracking
WHERE court_type = 'supreme_court' AND year BETWEEN 2020 AND 2026;

-- After this, re-run:
--   make ingest-history START=2020 END=2026 COURT=supreme_court SUBTYPE=precedent


-- =============================================
-- 7. RESET CONTENT HASHES (force re-process without deleting data)
-- ==============================================
-- Sets content_hash to NULL so the ingestion pipeline will re-process
-- and upsert (update) all documents for that year.

-- Reset hashes for one year
UPDATE case_law SET content_hash = NULL
WHERE court_type = 'supreme_court' AND case_year = 2026;

-- Reset hashes for multiple years (e.g. force re-process 2025 + 2026)
UPDATE case_law SET content_hash = NULL
WHERE case_year IN (2025, 2026);

-- Reset hashes for a single document
UPDATE case_law SET content_hash = NULL
WHERE case_id = 'KKO:2025:5';

-- After this, re-run the ingest command — all documents with NULL hash will be re-processed.


-- =============================================
-- 8. USEFUL COUNTS & HEALTH CHECKS
-- =============================================

-- Total documents per decision_type
SELECT decision_type, COUNT(*) AS total
FROM case_law
WHERE court_type = 'supreme_court'
GROUP BY decision_type;

-- Documents with embeddings vs without
SELECT
    cl.case_year,
    COUNT(DISTINCT cl.id) AS total_docs,
    COUNT(DISTINCT cs.case_law_id) AS docs_with_sections
FROM case_law cl
LEFT JOIN case_law_sections cs ON cs.case_law_id = cl.id
WHERE cl.court_type = 'supreme_court'
GROUP BY cl.case_year
ORDER BY cl.case_year DESC;

-- Orphaned sections (sections whose parent case_law was deleted)
SELECT cs.id, cs.case_law_id
FROM case_law_sections cs
LEFT JOIN case_law cl ON cl.id = cs.case_law_id
WHERE cl.id IS NULL;

-- ==========================================================================
-- Backfill empty legal_domains from title (no re-ingestion needed)
-- ==========================================================================
-- Preview: see which cases have empty legal_domains but a non-empty title
SELECT case_id, title, legal_domains
FROM case_law
WHERE (legal_domains IS NULL OR legal_domains = '{}')
  AND title IS NOT NULL AND title != ''
ORDER BY case_year DESC
LIMIT 50;

-- Count of affected cases
SELECT COUNT(*) AS cases_with_empty_keywords
FROM case_law
WHERE (legal_domains IS NULL OR legal_domains = '{}')
  AND title IS NOT NULL AND title != '';

-- ==========================================================================
-- BACKFILL ALL METADATA (run these in order — no re-ingestion needed!)
-- ==========================================================================

-- Step A: Backfill judgment from case_law_sections (section_type = 'judgment')
-- Preview first:
SELECT c.case_id, LEFT(s.content, 100) AS judgment_preview
FROM case_law c
JOIN case_law_sections s ON s.case_law_id = c.id AND s.section_type = 'judgment'
WHERE (c.judgment IS NULL OR c.judgment = '')
LIMIT 10;

-- Execute:
UPDATE case_law c
SET judgment = sub.content
FROM (
    SELECT DISTINCT ON (case_law_id) case_law_id, LEFT(content, 2000) AS content
    FROM case_law_sections
    WHERE section_type = 'judgment' AND content IS NOT NULL AND content != ''
    ORDER BY case_law_id, id
) sub
WHERE c.id = sub.case_law_id
  AND (c.judgment IS NULL OR c.judgment = '');

-- Step B: Backfill background_summary from case_law_sections (section_type = 'background' or 'summary')
UPDATE case_law c
SET background_summary = sub.content
FROM (
    SELECT DISTINCT ON (case_law_id) case_law_id, LEFT(content, 2000) AS content
    FROM case_law_sections
    WHERE section_type IN ('background', 'summary') AND content IS NOT NULL AND content != ''
    ORDER BY case_law_id, id
) sub
WHERE c.id = sub.case_law_id
  AND (c.background_summary IS NULL OR c.background_summary = '');

-- Step C: Backfill descriptive title from the first section's content (first line)
-- Only for cases with generic titles like "KKO 2024:76"
UPDATE case_law c
SET title = sub.first_line
FROM (
    SELECT DISTINCT ON (s.case_law_id)
        s.case_law_id,
        LEFT(split_part(s.content, E'\n', 1), 300) AS first_line
    FROM case_law_sections s
    JOIN case_law cl ON cl.id = s.case_law_id
    WHERE s.section_type IN ('background', 'summary', 'other')
      AND s.content IS NOT NULL AND s.content != ''
      AND s.content LIKE '% - %'
      AND (cl.title ~ '^[A-Z]{2,4}\s?\d{4}:\d+' OR cl.title IS NULL OR cl.title = '')
    ORDER BY s.case_law_id, s.id
) sub
WHERE c.id = sub.case_law_id
  AND LENGTH(sub.first_line) > 10
  AND sub.first_line LIKE '% - %';

-- Step D: Backfill legal_domains from title (for cases with descriptive titles)
UPDATE case_law
SET legal_domains = string_to_array(title, ' - ')
WHERE (legal_domains IS NULL OR legal_domains = '{}')
  AND title IS NOT NULL AND title != ''
  AND title LIKE '% - %';

-- Step E: Verify results (basic)
SELECT
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE judgment IS NOT NULL AND judgment != '') AS has_judgment,
    COUNT(*) FILTER (WHERE background_summary IS NOT NULL AND background_summary != '') AS has_background,
    COUNT(*) FILTER (WHERE legal_domains IS NOT NULL AND legal_domains != '{}') AS has_keywords,
    COUNT(*) FILTER (WHERE title LIKE '% - %') AS has_descriptive_title
FROM case_law;


-- ==========================================================================
-- BACKFILL METADATA FROM full_text (no re-ingestion needed!)
-- ==========================================================================
-- These queries extract structured data from the full_text column already
-- stored in Supabase. Run in Supabase SQL Editor in batches (LIMIT).
-- Repeat each batch until the count stops increasing.
--
-- IMPORTANT: All queries use POSITION/SUBSTRING (fast string ops) instead
-- of complex regex to avoid Supabase SQL Editor timeout (60s limit).
-- Queries with LIMIT should be run REPEATEDLY until no more rows change.

-- -------------------------------------------------------------------------
-- Step F: decision_outcome — from Tuomiolauselma/Päätöslauselma section
-- -------------------------------------------------------------------------
-- CRITICAL: Only classifies from the ACTUAL judgment section header,
-- NOT the entire full_text. Phrases like "valitus hylätään" appear in
-- party demands and lower court summaries and would misclassify if
-- searched across the full text.
--
-- Coverage: ~5,153 cases have Tuomiolauselma/Päätöslauselma (mostly 1985+)
-- Verified results across 13,222 cases:
--   not_changed:             2,147  "ei muuteta" / "jää pysyväksi"
--   overturned:              1,192  "kumotaan" (without remand)
--   modified:                  685  "muutetaan"
--   overturned_and_remanded:   564  "kumotaan" + "palautetaan"
--   dismissed:                 110  "hylätään"
--   remanded:                   39  "palautetaan" (without overturn)
--   not_examined:               33  "jätetään tutkimatta"
--   NULL:                    8,452  no section found or unclassifiable (safe)

-- Run repeatedly until count stops growing (batches of 500):
UPDATE case_law c
SET decision_outcome = t.new_outcome
FROM (
    SELECT
        cl.id,
        CASE
            WHEN outcome_text ~* 'ei muuteta|ei muutettu|jää pysyväksi'
                THEN 'not_changed'
            WHEN outcome_text ~* 'kumotaan|kumottiin' AND outcome_text ~* 'palautetaan|palauttaa'
                THEN 'overturned_and_remanded'
            WHEN outcome_text ~* 'kumotaan|kumottiin'
                THEN 'overturned'
            WHEN outcome_text ~* 'muutetaan|muutettu|muutos'
                THEN 'modified'
            WHEN outcome_text ~* 'hylätään|hylättiin'
                THEN 'dismissed'
            WHEN outcome_text ~* 'jätetään tutkimatta'
                THEN 'not_examined'
            WHEN outcome_text ~* 'palautetaan|palautettiin|palauttaa'
                THEN 'remanded'
            ELSE NULL
        END AS new_outcome
    FROM case_law cl
    CROSS JOIN LATERAL (
        SELECT SUBSTRING(
            cl.full_text
            FROM CASE
                WHEN cl.full_text LIKE '%Tuomiolauselma%'
                THEN POSITION('Tuomiolauselma' IN cl.full_text) + 15
                ELSE POSITION('Päätöslauselma' IN cl.full_text) + 15
            END
            FOR 500
        ) AS outcome_text
    ) sub
    WHERE (cl.full_text LIKE '%Tuomiolauselma%' OR cl.full_text LIKE '%Päätöslauselma%')
      AND (cl.decision_outcome IS NULL OR cl.decision_outcome = '')
    LIMIT 500
) t
WHERE c.id = t.id
  AND t.new_outcome IS NOT NULL;

-- -------------------------------------------------------------------------
-- Step G: dissenting_opinion + dissenting_text — from "Eri mieltä" section
-- -------------------------------------------------------------------------
-- Two-step process:
-- 1) Set flag + extract text for cases with "Eri mieltä" section
-- 2) Set flag only for cases with "(Ään.)" marker but no text section

-- Step G1: Flag + text (run repeatedly until count stops):
UPDATE case_law
SET
    dissenting_opinion = TRUE,
    dissenting_text = LEFT(
        SUBSTRING(full_text FROM POSITION('Eri mieltä' IN full_text) FOR 2000),
        2000
    )
WHERE (dissenting_opinion IS NULL OR dissenting_opinion = FALSE)
  AND full_text LIKE '%Eri mieltä%'
  AND id IN (
      SELECT id FROM case_law
      WHERE (dissenting_opinion IS NULL OR dissenting_opinion = FALSE)
        AND full_text LIKE '%Eri mieltä%'
      LIMIT 500
  );

-- Step G2: Flag only for (Ään.) cases without "Eri mieltä" section:
UPDATE case_law
SET dissenting_opinion = TRUE
WHERE (dissenting_opinion IS NULL OR dissenting_opinion = FALSE)
  AND (full_text LIKE '%(Ään.)%' OR full_text LIKE '%(Ään)%');

-- Step G3: Fill missing dissent text for already-flagged cases:
UPDATE case_law
SET dissenting_text = LEFT(
    SUBSTRING(full_text FROM POSITION('Eri mieltä' IN full_text) FOR 2000),
    2000
)
WHERE dissenting_opinion = TRUE
  AND (dissenting_text IS NULL OR dissenting_text = '')
  AND full_text LIKE '%Eri mieltä%'
  AND id IN (
      SELECT id FROM case_law
      WHERE dissenting_opinion = TRUE
        AND (dissenting_text IS NULL OR dissenting_text = '')
        AND full_text LIKE '%Eri mieltä%'
      LIMIT 500
  );

-- -------------------------------------------------------------------------
-- Step H: background_summary — from "Asian tausta" section
-- -------------------------------------------------------------------------
-- Uses POSITION/SUBSTRING (fast, no regex). Run repeatedly until done:
UPDATE case_law c
SET background_summary = LEFT(
    SUBSTRING(
        c.full_text
        FROM CASE
            WHEN c.full_text LIKE '%Asian tausta ja kysymyksenasettelu%'
            THEN POSITION('Asian tausta ja kysymyksenasettelu' IN c.full_text) + 34
            WHEN c.full_text LIKE '%Asian tausta%'
            THEN POSITION('Asian tausta' IN c.full_text) + 12
            ELSE POSITION('Asian käsittely alemmissa oikeuksissa' IN c.full_text) + 37
        END
        FOR 2000
    ),
    2000
)
WHERE (c.background_summary IS NULL OR c.background_summary = '')
  AND (c.full_text LIKE '%Asian tausta%' OR c.full_text LIKE '%Asian käsittely alemmissa%')
  AND c.id IN (
      SELECT id FROM case_law
      WHERE (background_summary IS NULL OR background_summary = '')
        AND (full_text LIKE '%Asian tausta%' OR full_text LIKE '%Asian käsittely alemmissa%')
      LIMIT 500
  );

-- -------------------------------------------------------------------------
-- Step I: cited_laws — standalone header lines with § symbol
-- -------------------------------------------------------------------------
-- Extracts law citation lines (e.g. "RL 41 luku 2 §") from the header
-- section (before "Asian käsittely" or first 2000 chars).
-- Uses positive regex matching only law abbreviation patterns.
-- Run in year-range batches to avoid timeout:

-- Batch 1: years 2000+
UPDATE case_law c
SET cited_laws = sub.laws
FROM (
    SELECT
        cl.id,
        ARRAY(
            SELECT DISTINCT TRIM(m[1])
            FROM regexp_matches(
                SUBSTRING(cl.full_text FROM 1 FOR LEAST(
                    COALESCE(NULLIF(POSITION('Asian käsittely' IN cl.full_text), 0), 2000),
                    2000
                )),
                '(?:^|\n)\s*([A-ZÄÖÅ][A-Za-zÄÖÅäöå\-]*L?\s+\d[^\n]*§[^\n]*)',
                'g'
            ) AS m
        ) AS laws
    FROM case_law cl
    WHERE (cl.cited_laws IS NULL OR cl.cited_laws = '{}')
      AND cl.case_year >= 2000
) sub
WHERE c.id = sub.id
  AND array_length(sub.laws, 1) > 0;

-- Batch 2: years 1980-1999
-- (same query, change: AND cl.case_year BETWEEN 1980 AND 1999)

-- Batch 3: years before 1980
-- (same query, change: AND cl.case_year < 1980)

-- -------------------------------------------------------------------------
-- Step J: cited_cases — KKO/KHO cross-references
-- -------------------------------------------------------------------------
-- Extracts references to other Supreme Court decisions from full_text.
-- Excludes self-references (the case's own case_id).
UPDATE case_law c
SET cited_cases = sub.refs
FROM (
    SELECT
        cl.id,
        ARRAY(
            SELECT DISTINCT m[1]
            FROM regexp_matches(cl.full_text, '((?:KKO|KHO)[: ]\d{4}[: ]\d+)', 'g') AS m
            WHERE m[1] != cl.case_id
        ) AS refs
    FROM case_law cl
    WHERE (cl.cited_cases IS NULL OR cl.cited_cases = '{}')
      AND (cl.full_text LIKE '%KKO%' OR cl.full_text LIKE '%KHO%')
    LIMIT 200
) sub
WHERE c.id = sub.id
  AND array_length(sub.refs, 1) > 0;

-- =============================================
-- 9. FIND UNPROCESSED YEARS / INCOMPLETE INGESTIONS
-- =============================================
-- Run this to find years where documents exist in JSON but are missing from
-- Supabase, or where tracking says there are still remaining documents.
-- This is crucial before going to production — it answers:
--   "Is there any year or document that still needs to be processed?"

-- ── 9a. Years with incomplete ingestion (remaining > 0) ──
-- Shows every year/court/type where tracking says some docs are NOT yet in Supabase.
SELECT
    court_type,
    decision_type,
    year,
    status,
    total_cases,
    processed_cases,
    failed_cases,
    GREATEST(0, total_cases - processed_cases) AS remaining,
    ROUND(
        CASE WHEN total_cases > 0
             THEN (processed_cases::NUMERIC / total_cases) * 100
             ELSE 0
        END, 1
    ) AS pct_done,
    completed_at
FROM case_law_ingestion_tracking
WHERE total_cases > processed_cases
   OR status NOT IN ('completed', 'skipped')
ORDER BY year DESC, court_type, decision_type;

-- ── 9b. Years with failed documents that were never retried ──
SELECT
    t.court_type,
    t.decision_type,
    t.year,
    t.failed_cases,
    COUNT(e.id) AS error_count,
    string_agg(DISTINCT e.error_type, ', ') AS error_types
FROM case_law_ingestion_tracking t
LEFT JOIN case_law_ingestion_errors e ON e.tracking_id = t.id
WHERE t.failed_cases > 0
GROUP BY t.court_type, t.decision_type, t.year, t.failed_cases
ORDER BY t.year DESC;

-- ── 9c. Documents in case_law that have 0 sections (metadata stored, but
--        sections failed — e.g. embedding timeout). These need re-ingestion. ──
SELECT
    cl.case_id,
    cl.court_type,
    cl.case_year,
    cl.decision_type,
    cl.title
FROM case_law cl
LEFT JOIN case_law_sections cs ON cs.case_law_id = cl.id
WHERE cs.id IS NULL
ORDER BY cl.case_year DESC, cl.case_id;

-- ── 9d. Year-level coverage gap: compare tracking totals to actual counts ──
-- If tracking says total=50 but actual=45, then 5 documents were never stored.
SELECT
    t.court_type,
    t.decision_type,
    t.year,
    t.total_cases AS expected,
    COUNT(c.id) AS actual_in_db,
    GREATEST(0, t.total_cases - COUNT(c.id)) AS missing_from_db,
    t.status
FROM case_law_ingestion_tracking t
LEFT JOIN case_law c
    ON  c.court_type    = t.court_type
    AND c.decision_type = t.decision_type
    AND c.case_year     = t.year
GROUP BY t.court_type, t.decision_type, t.year, t.total_cases, t.status
HAVING t.total_cases > COUNT(c.id)
ORDER BY t.year DESC, t.court_type, t.decision_type;

-- ── 9e. Quick summary: overall ingestion health ──
SELECT
    COUNT(*)                                                         AS total_tracking_rows,
    COUNT(*) FILTER (WHERE status = 'completed')                     AS completed,
    COUNT(*) FILTER (WHERE status = 'in_progress')                   AS in_progress,
    COUNT(*) FILTER (WHERE status = 'pending')                       AS pending,
    COUNT(*) FILTER (WHERE status = 'failed')                        AS failed,
    SUM(total_cases)                                                 AS total_expected,
    SUM(processed_cases)                                             AS total_processed,
    SUM(failed_cases)                                                AS total_failed,
    SUM(GREATEST(0, total_cases - processed_cases))                  AS total_remaining
FROM case_law_ingestion_tracking;


-- -------------------------------------------------------------------------
-- Step K: Verify all columns after backfill
-- -------------------------------------------------------------------------
SELECT
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE judgment IS NOT NULL AND judgment != '') AS has_judgment,
    COUNT(*) FILTER (WHERE background_summary IS NOT NULL AND background_summary != '') AS has_background,
    COUNT(*) FILTER (WHERE legal_domains IS NOT NULL AND legal_domains != '{}') AS has_keywords,
    COUNT(*) FILTER (WHERE title LIKE '% - %') AS has_descriptive_title,
    COUNT(*) FILTER (WHERE decision_outcome IS NOT NULL AND decision_outcome != '') AS has_decision_outcome,
    COUNT(*) FILTER (WHERE judges IS NOT NULL AND judges != '') AS has_judges,
    COUNT(*) FILTER (WHERE dissenting_opinion = TRUE) AS has_dissent,
    COUNT(*) FILTER (WHERE dissenting_text IS NOT NULL AND dissenting_text != '') AS has_dissent_text,
    COUNT(*) FILTER (WHERE cited_laws IS NOT NULL AND cited_laws != '{}') AS has_cited_laws,
    COUNT(*) FILTER (WHERE cited_cases IS NOT NULL AND cited_cases != '{}') AS has_cited_cases
FROM case_law;
