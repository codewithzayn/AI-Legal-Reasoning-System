-- Add Phase 1 structured legal intelligence columns to legal_chunks
-- This enables intelligent legal reasoning beyond simple text search

ALTER TABLE legal_chunks ADD COLUMN IF NOT EXISTS (
    -- Phase 1: Definitions extracted from statutes
    definitions JSONB DEFAULT '[]'::jsonb,

    -- Phase 1: Cross-references to other statutes
    cross_references JSONB DEFAULT '[]'::jsonb,

    -- Phase 1: Temporal scope (effective dates, in force status)
    temporal_scope JSONB DEFAULT '{}'::jsonb,

    -- Phase 1: Amendment tracking (insertions, repeals, substitutions)
    amendments JSONB DEFAULT '{}'::jsonb,

    -- Metadata: legal concepts/tags for filtering
    legal_concepts TEXT[] DEFAULT ARRAY[]::TEXT[],

    -- Metadata: extraction timestamp
    extracted_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS legal_chunks_definitions_idx
    ON legal_chunks USING GIN (definitions);

CREATE INDEX IF NOT EXISTS legal_chunks_cross_references_idx
    ON legal_chunks USING GIN (cross_references);

CREATE INDEX IF NOT EXISTS legal_chunks_temporal_scope_idx
    ON legal_chunks USING GIN (temporal_scope);

CREATE INDEX IF NOT EXISTS legal_chunks_amendments_idx
    ON legal_chunks USING GIN (amendments);

CREATE INDEX IF NOT EXISTS legal_chunks_concepts_idx
    ON legal_chunks USING GIN (legal_concepts);

COMMENT ON COLUMN legal_chunks.definitions IS 'Phase 1: Key terms and definitions extracted from document';
COMMENT ON COLUMN legal_chunks.cross_references IS 'Phase 1: References to other statutes and regulations';
COMMENT ON COLUMN legal_chunks.temporal_scope IS 'Phase 1: Effective dates, entry into force, in-force status';
COMMENT ON COLUMN legal_chunks.amendments IS 'Phase 1: Amendment actions: insertions, repeals, substitutions';
COMMENT ON COLUMN legal_chunks.legal_concepts IS 'Tags for intelligent categorization: employment, tax, etc.';
