-- UI tables for LexAI feedback and conversation persistence
-- Run this in the Supabase SQL editor

CREATE TABLE IF NOT EXISTS feedback (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    message_content TEXT NOT NULL,
    query TEXT,
    rating TEXT NOT NULL CHECK (rating IN ('up', 'down')),
    lang TEXT DEFAULT 'fi',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS conversations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'Untitled',
    messages_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    lang TEXT DEFAULT 'fi',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Index for listing conversations by date
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations (updated_at DESC);

-- Index for feedback analytics
CREATE INDEX IF NOT EXISTS idx_feedback_created_at ON feedback (created_at DESC);
