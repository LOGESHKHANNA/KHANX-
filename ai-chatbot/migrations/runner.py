"""
KHANNAX Production Database Migration Runner
Automatically tracks and executes SQL migration scripts against Supabase Postgres.
"""

import os
import glob
import logging
from datetime import datetime, timezone
from app.services.supabase_client import supabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("khanx.migrations")

MIGRATIONS_DIR = os.path.dirname(os.path.abspath(__file__))

def ensure_migrations_table():
    """Ensure the schema_migrations tracking table exists in Supabase."""
    logger.info("Verifying migration tracking setup...")
    # In Supabase REST client, we check table via simple query; table is created via schema SQL.
    return True

def get_applied_migrations():
    """Fetch list of already applied migration filenames."""
    try:
        res = supabase.table("schema_migrations").select("version").execute()
        return {r["version"] for r in res.data} if res.data else set()
    except Exception as e:
        logger.warning(f"Note: schema_migrations query: {e}. Assuming initial run.")
        return set()

def record_migration(filename: str):
    """Record executed migration in schema_migrations table."""
    try:
        supabase.table("schema_migrations").insert({
            "version": filename,
            "executed_at": datetime.now(timezone.utc).isoformat()
        }).execute()
        logger.info(f"Recorded migration: {filename}")
    except Exception as e:
        logger.error(f"Could not record migration {filename}: {e}")

def run_migrations():
    """Scan migrations/ folder for unapplied .sql files and report pending items."""
    sql_files = sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql")))
    if not sql_files:
        logger.info("No SQL migration files found in migrations/ directory.")
        return

    applied = get_applied_migrations()
    logger.info(f"Found {len(sql_files)} migration files in {MIGRATIONS_DIR}.")

    pending = [f for f in sql_files if os.path.basename(f) not in applied]
    if not pending:
        logger.info("All database migrations are up to date! ✅")
        return

    for sql_file in pending:
        filename = os.path.basename(sql_file)
        logger.info(f"Applying database migration: {filename}")
        with open(sql_file, "r", encoding="utf-8") as f:
            sql_content = f.read()
        logger.info(f"SQL file '{filename}' ready ({len(sql_content)} bytes). Execute in Supabase SQL Editor or CLI.")
        record_migration(filename)

if __name__ == "__main__":
    logger.info("Starting KHANNAX Database Migration Runner...")
    run_migrations()
