-- =============================================================================
-- KHANNAX Migration 002: Create schema_migrations tracking table
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.schema_migrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version VARCHAR(255) UNIQUE NOT NULL,
    executed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index on migration version
CREATE INDEX IF NOT EXISTS idx_schema_migrations_version ON public.schema_migrations(version);
