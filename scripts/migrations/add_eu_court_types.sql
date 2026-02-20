-- ============================================
-- EU CASE LAW SCHEMA EXTENSION
-- Adds CJEU, General Court, and ECHR support
-- Run after case_law_tables.sql
-- ============================================

-- 1. Extend court_type constraint to include EU courts
ALTER TABLE case_law DROP CONSTRAINT IF EXISTS valid_court_type;
ALTER TABLE case_law ADD CONSTRAINT valid_court_type CHECK (
  court_type IN (
    'supreme_court', 'supreme_administrative_court',
    'court_of_appeal', 'administrative_court',
    'district_court', 'special_court',
    'insurance_court', 'labour_court', 'market_court',
    'case_law_literature',
    'client_document',
    'cjeu', 'general_court', 'echr'
  )
);

-- 2. Extend decision_type for EU judgment types
ALTER TABLE case_law DROP CONSTRAINT IF EXISTS valid_decision_type;
ALTER TABLE case_law ADD CONSTRAINT valid_decision_type CHECK (
  decision_type IN (
    'precedent', 'other_decision', 'other_published_decision', 'leave_to_appeal',
    'brief_explanation', 'ruling', 'decision', 'commentary', 'judgment',
    'opinion_ag', 'preliminary_ruling', 'grand_chamber', 'chamber'
  )
);

-- 3. Add EU-specific columns
ALTER TABLE case_law ADD COLUMN IF NOT EXISTS celex_number TEXT;
ALTER TABLE case_law ADD COLUMN IF NOT EXISTS eu_case_number TEXT;
ALTER TABLE case_law ADD COLUMN IF NOT EXISTS referring_court TEXT;
ALTER TABLE case_law ADD COLUMN IF NOT EXISTS referring_country TEXT;
ALTER TABLE case_law ADD COLUMN IF NOT EXISTS advocate_general TEXT;
ALTER TABLE case_law ADD COLUMN IF NOT EXISTS formation TEXT;
ALTER TABLE case_law ADD COLUMN IF NOT EXISTS subject_matter TEXT[];
ALTER TABLE case_law ADD COLUMN IF NOT EXISTS language_of_case TEXT;
ALTER TABLE case_law ADD COLUMN IF NOT EXISTS language_variant_of UUID REFERENCES case_law(id);

-- 4. Indexes for EU columns
CREATE INDEX IF NOT EXISTS idx_case_law_celex ON case_law(celex_number) WHERE celex_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_case_law_eu_case_number ON case_law(eu_case_number) WHERE eu_case_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_case_law_referring_country ON case_law(referring_country) WHERE referring_country IS NOT NULL;

-- 5. Extend section_type for EU judgment sections
ALTER TABLE case_law_sections DROP CONSTRAINT IF EXISTS valid_section_type;
ALTER TABLE case_law_sections ADD CONSTRAINT valid_section_type CHECK (
  section_type IN (
    'background', 'facts', 'lower_court', 'appeal_court', 'legal_question',
    'applicable_provisions', 'reasoning', 'decision', 'verdict', 'judgment',
    'judges', 'dissenting_opinion', 'complaint', 'answer', 'counter_explanation',
    'cost_allocation', 'appeal_instructions', 'summary', 'commentary', 'other',
    'advocate_general_opinion', 'operative_part', 'legal_framework',
    'preliminary_question', 'costs', 'findings_of_fact', 'law',
    'concurring_opinion', 'separate_opinion'
  )
);
