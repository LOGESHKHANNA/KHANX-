-- Migration 001: Performance Indexes, Schema Alignment, and Supabase Storage setup
-- Run this script in your Supabase Dashboard -> SQL Editor

-- 1. Add missing columns
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now());
ALTER TABLE documents ADD COLUMN IF NOT EXISTS file_type TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS file_size BIGINT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS storage_path TEXT;

-- 2. Add performance indexes for high-volume lookups
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id, uploaded_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_tasks_user_id ON user_tasks(user_id, status);
CREATE INDEX IF NOT EXISTS idx_email_drafts_user_id ON email_drafts(user_id);

-- 3. Create private Supabase Storage bucket for user documents
INSERT INTO storage.buckets (id, name, public)
VALUES ('documents', 'documents', false)
ON CONFLICT (id) DO NOTHING;

-- 4. Enable Row Level Security (RLS) policies on Storage bucket
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can upload their own document files') THEN
    CREATE POLICY "Users can upload their own document files" ON storage.objects
    FOR INSERT WITH CHECK (bucket_id = 'documents' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can read their own document files') THEN
    CREATE POLICY "Users can read their own document files" ON storage.objects
    FOR SELECT USING (bucket_id = 'documents' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can delete their own document files') THEN
    CREATE POLICY "Users can delete their own document files" ON storage.objects
    FOR DELETE USING (bucket_id = 'documents' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;
END $$;
