-- =============================================================================
-- Migration: Add user authentication support
-- Adds user_id column to conversations and feedback tables.
-- Enables Row Level Security (RLS) for per-user data isolation.
--
-- Run ONCE against your Supabase project:
--   psql $DATABASE_URL -f scripts/migrations/add_user_auth.sql
-- =============================================================================

-- 1. Add user_id column to conversations (nullable for backward compat)
ALTER TABLE conversations
  ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE;

-- 2. Add user_id column to feedback (nullable, analytics-oriented)
ALTER TABLE feedback
  ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES auth.users(id) ON DELETE SET NULL;

-- 3. Index for fast user-scoped queries
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_feedback_user_id ON feedback(user_id);

-- 4. Enable RLS on conversations
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

-- Authenticated users see only their own conversations
CREATE POLICY conversations_select_own ON conversations
  FOR SELECT USING (user_id = auth.uid());

CREATE POLICY conversations_insert_own ON conversations
  FOR INSERT WITH CHECK (user_id = auth.uid());

CREATE POLICY conversations_update_own ON conversations
  FOR UPDATE USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY conversations_delete_own ON conversations
  FOR DELETE USING (user_id = auth.uid());

-- Service role bypasses RLS automatically; no extra policy needed.

-- 5. Enable RLS on feedback
ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;

CREATE POLICY feedback_insert_own ON feedback
  FOR INSERT WITH CHECK (user_id = auth.uid());

CREATE POLICY feedback_select_own ON feedback
  FOR SELECT USING (user_id = auth.uid());

-- =============================================================================
-- Backfill: assign existing conversations to a specific user (optional)
-- Replace '<YOUR_USER_UUID>' with an actual auth.users id.
--
-- UPDATE conversations SET user_id = '<YOUR_USER_UUID>' WHERE user_id IS NULL;
-- UPDATE feedback SET user_id = '<YOUR_USER_UUID>' WHERE user_id IS NULL;
-- =============================================================================
