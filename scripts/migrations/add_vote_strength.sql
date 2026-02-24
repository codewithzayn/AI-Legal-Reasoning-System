-- Add vote strength tracking columns to case_law table
-- Enables lawyers to assess precedent strength (e.g., 4-1 split vs 5-0 unanimous)

-- Check if columns exist before adding (for idempotency)
DO $$ BEGIN
    -- Add judges_total if not exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'case_law' AND column_name = 'judges_total') THEN
        ALTER TABLE case_law ADD COLUMN judges_total INTEGER DEFAULT 0;
        COMMENT ON COLUMN case_law.judges_total IS 'Total number of judges who decided the case';
    END IF;

    -- Add judges_dissenting if not exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'case_law' AND column_name = 'judges_dissenting') THEN
        ALTER TABLE case_law ADD COLUMN judges_dissenting INTEGER DEFAULT 0;
        COMMENT ON COLUMN case_law.judges_dissenting IS 'Number of dissenting judges';
    END IF;

    -- Add vote_strength if not exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'case_law' AND column_name = 'vote_strength') THEN
        ALTER TABLE case_law ADD COLUMN vote_strength TEXT DEFAULT '';
        COMMENT ON COLUMN case_law.vote_strength IS 'Vote ratio as string (e.g., "4-1", "5-0", "3-2")';
    END IF;
END $$;

-- Create index on vote_strength for fast queries about weak precedents
CREATE INDEX IF NOT EXISTS idx_case_law_vote_strength ON case_law(vote_strength);

-- Create index on judges_total for filtering by court composition
CREATE INDEX IF NOT EXISTS idx_case_law_judges_total ON case_law(judges_total);
