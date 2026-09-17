import os
from pydantic_settings import BaseSettings, SettingsConfigDict

# Support loading .env from current directory or relative to config.py
env_paths = [
    ".env",
    os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
]

class Settings(BaseSettings):
    # ── Core credentials (REQUIRED) ────────────────────────────────────────
    SUPABASE_URL: str
    SUPABASE_KEY: str          # anon/public key — safe to expose to frontend
    GROQ_API_KEY: str = ""

    # ── Error Monitoring (Sentry) ──────────────────────────────────────────
    # Set SENTRY_DSN in production for real-time error tracking & performance monitoring.
    SENTRY_DSN: str = ""

    # ── Storage ────────────────────────────────────────────────────────────
    # Name of the Supabase Storage bucket for user document uploads.
    # Create this bucket in your Supabase project → Storage → New Bucket.
    # Set bucket to PRIVATE and enable RLS (see migrations/001_indexes_and_storage.sql).
    SUPABASE_STORAGE_BUCKET: str = "documents"

    # ── Security (Production) ──────────────────────────────────────────────
    # Set FORCE_HTTPS=true in production to enforce HTTPS redirect.
    FORCE_HTTPS: bool = False

    # Comma-separated list of allowed CORS origins.
    # Example: ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
    # Leave empty for localhost-only development defaults.
    ALLOWED_ORIGINS: str = ""

    # ── Redis (Production Caching & Scalable Rate Limiting) ────────────────
    # URL connection string for Redis server.
    # Example: REDIS_URL=redis://localhost:6379/0 or redis://:password@redis-host:6379/0
    REDIS_URL: str = ""


    model_config = SettingsConfigDict(env_file=env_paths, env_file_encoding="utf-8", extra="ignore")

settings = Settings()
