# KHANNAX Production Backup & Recovery Runbook

This runbook outlines standard operating procedures (SOP) for backing up and restoring data on the KHANNAX AI platform.

---

## Data Assets Summary

| Asset | Location | Storage Type | Frequency |
| :--- | :--- | :--- | :--- |
| **Vector DB (ChromaDB)** | `./chroma_data` | Persistent SQLite + HNSW files | Daily / Pre-deploy |
| **User File Uploads** | `./uploads` & Supabase Storage | Persistent files / S3 bucket | Daily |
| **Relational Database** | Supabase Postgres (`chat_sessions`, `chat_messages`, `documents`) | Managed Postgres DB | Automatic daily snapshots |
| **Database Migrations** | `./migrations` | Version-controlled SQL scripts | Per release |

---

## Backup Procedures

### 1. Automated Local & Vector Snapshot
Run the automated snapshot script to archive vector embeddings, uploaded files, and migration files into a timestamped `.tar.gz` bundle:

```bash
python scripts/backup.py
```

- Output archive location: `backups/khanx_backup_YYYYMMDD_HHMMSS.tar.gz`

### 2. Supabase Database Backup
- **Supabase Dashboard**: Navigate to **Project Settings -> Database -> Backups**.
- **Supabase CLI Dump**:
  ```bash
  supabase db dump --data-only > backups/supabase_data_dump.sql
  ```

---

## Disaster Recovery & Restoration Procedure

### Step 1: Stop Running Application Services
```bash
docker-compose down
```

### Step 2: Restore Vector Store (`chroma_data`) & Uploads
1. Identify the target backup file in `backups/`.
2. Extract the archive into the root application folder:
   ```bash
   tar -xzf backups/khanx_backup_YYYYMMDD_HHMMSS.tar.gz -C .
   ```

### Step 3: Restore Database Schema & Data
1. Apply any pending database migrations using the migration runner:
   ```bash
   python -m migrations.runner
   ```
2. If restoring from a Supabase CLI SQL dump:
   ```bash
   supabase db reset
   psql -h <SUPABASE_HOST> -U postgres -d postgres -f backups/supabase_data_dump.sql
   ```

### Step 4: Restart Application & Verify Health
```bash
docker-compose up --build -d
curl http://localhost:8000/health
```
