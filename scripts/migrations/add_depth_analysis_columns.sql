-- Add depth analysis columns to case_law (exceptions, weighted_factors, trend, distinctive_facts)
-- For KKO/KHO legal analysis: exceptions, reasoning excerpt, trend direction, key facts.

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'case_law' AND column_name = 'exceptions') THEN
        ALTER TABLE case_law ADD COLUMN exceptions TEXT DEFAULT '';
        COMMENT ON COLUMN case_law.exceptions IS 'Extracted exception/limitation phrases (e.g. Poikkeuksena, Pois lukien) for legal analysis';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'case_law' AND column_name = 'weighted_factors') THEN
        ALTER TABLE case_law ADD COLUMN weighted_factors TEXT DEFAULT '';
        COMMENT ON COLUMN case_law.weighted_factors IS 'Reasoning excerpt or weighted factors summary for precedent analysis';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'case_law' AND column_name = 'trend_direction') THEN
        ALTER TABLE case_law ADD COLUMN trend_direction TEXT DEFAULT '';
        COMMENT ON COLUMN case_law.trend_direction IS 'Trend vs earlier cases: stricter, more lenient, stable (optional, for future use)';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'case_law' AND column_name = 'distinctive_facts') THEN
        ALTER TABLE case_law ADD COLUMN distinctive_facts TEXT DEFAULT '';
        COMMENT ON COLUMN case_law.distinctive_facts IS 'Key/distinctive facts that drove the outcome';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'case_law' AND column_name = 'ruling_instruction') THEN
        ALTER TABLE case_law ADD COLUMN ruling_instruction TEXT DEFAULT '';
        COMMENT ON COLUMN case_law.ruling_instruction IS 'Brief ruling instruction / central legal rule from Judgment section';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'case_law' AND column_name = 'applied_provisions') THEN
        ALTER TABLE case_law ADD COLUMN applied_provisions TEXT DEFAULT '';
        COMMENT ON COLUMN case_law.applied_provisions IS 'Statute/provision refs applied in reasoning (e.g. RL 46 § 1)';
    END IF;
END $$;
