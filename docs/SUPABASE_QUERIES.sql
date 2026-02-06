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

-- Check ingestion tracking status
SELECT court_type, decision_type, year, status, total_cases, processed_cases, last_processed_case, started_at, completed_at
FROM case_law_ingestion_tracking
ORDER BY year DESC, court_type;

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
-- 6. RESET CONTENT HASHES (force re-process without deleting data)
-- =============================================
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
-- 7. USEFUL COUNTS & HEALTH CHECKS
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
