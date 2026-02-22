-- =============================================================================
-- Migration: Atomic ingestion tracking helper function
--
-- Problem: The Python ingestion manager updated the tracking row AFTER each
-- successful case store, but the two writes (case_law insert + tracking update)
-- were not wrapped in a transaction.  A crash between them left the tracking
-- table with a stale counter that no longer matched reality.
--
-- Fix:
--   1. A stored procedure that increments processed_cases and updates
--      last_processed_case in a single atomic statement.
--   2. A stored procedure for atomic final-status writes (completed / partial).
--
-- These replace the two-step Python pattern:
--   store_case() → _track_status()   (was NOT atomic)
-- with a single RPC call to bump_ingestion_progress().
--
-- Run ONCE against your Supabase project:
--   psql $DATABASE_URL -f scripts/migrations/atomic_ingestion_tracking.sql
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. bump_ingestion_progress
--    Atomically increment processed_cases and record the last processed case.
--    Called once per successfully stored document.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION bump_ingestion_progress(
  p_tracking_id    uuid,
  p_last_case_id   text DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE case_law_ingestion_tracking
  SET
    processed_cases     = COALESCE(processed_cases, 0) + 1,
    last_processed_case = COALESCE(p_last_case_id, last_processed_case),
    last_updated        = now()
  WHERE id = p_tracking_id;
END;
$$;


-- ---------------------------------------------------------------------------
-- 2. bump_ingestion_failed
--    Atomically increment failed_cases.
--    Called once per failed document.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION bump_ingestion_failed(
  p_tracking_id uuid
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE case_law_ingestion_tracking
  SET
    failed_cases = COALESCE(failed_cases, 0) + 1,
    last_updated = now()
  WHERE id = p_tracking_id;
END;
$$;


-- ---------------------------------------------------------------------------
-- 3. finalize_ingestion_tracking
--    Write the final status (completed / partial / failed) and set
--    completed_at in a single statement.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION finalize_ingestion_tracking(
  p_tracking_id uuid,
  p_status      text,           -- 'completed', 'partial', 'failed'
  p_total_cases int DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE case_law_ingestion_tracking
  SET
    status       = p_status,
    total_cases  = COALESCE(p_total_cases, total_cases),
    completed_at = now(),
    last_updated = now()
  WHERE id = p_tracking_id;
END;
$$;
