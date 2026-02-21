-- Backfill metadata_fts from existing columns (no re-ingestion).
-- Run in Supabase SQL Editor. Safe to run multiple times.
--
-- Prerequisite: case_law_metadata_tsvector() must exist (from case_law_tables.sql).

-- Step 1: Add column if your schema uses a stored metadata_fts column (e.g. for RPCs)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'case_law' AND column_name = 'metadata_fts'
    ) THEN
        ALTER TABLE case_law ADD COLUMN metadata_fts tsvector;
        COMMENT ON COLUMN case_law.metadata_fts IS 'FTS over case_id, title, judgment, background, outcome, legal_domains, cited_*';
    END IF;
END $$;

-- Step 2: Backfill metadata_fts from existing columns (batch 1000 per run; run until 0 rows)
UPDATE case_law c
SET metadata_fts = case_law_metadata_tsvector(
    c.case_id, c.title, c.judgment, c.background_summary, c.decision_outcome,
    c.legal_domains, c.cited_cases, c.cited_laws, c.cited_eu_cases, c.cited_regulations
)
WHERE c.id IN (
    SELECT id FROM case_law b
    WHERE b.metadata_fts IS NULL
       OR b.metadata_fts IS DISTINCT FROM case_law_metadata_tsvector(
            b.case_id, b.title, b.judgment, b.background_summary, b.decision_outcome,
            b.legal_domains, b.cited_cases, b.cited_laws, b.cited_eu_cases, b.cited_regulations
          )
    LIMIT 1000
);

-- Step 3: Create GIN index on metadata_fts if you use the stored column for search
DROP INDEX IF EXISTS idx_case_law_metadata_fts;
CREATE INDEX IF NOT EXISTS idx_case_law_metadata_fts ON case_law USING GIN(metadata_fts);

-- Optional: reindex for consistency
-- REINDEX INDEX idx_case_law_metadata_fts;
