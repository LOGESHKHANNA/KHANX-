"""
KHANNAX Production Backup & Disaster Recovery Tool
Creates timestamped tar.gz archives of ChromaDB vector store, document uploads, and configuration.
"""

import os
import sys
import tarfile
import shutil
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

def create_backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_name = f"khanx_backup_{timestamp}.tar.gz"
    archive_path = os.path.join(BACKUP_DIR, archive_name)

    print(f"📦 Starting KHANNAX backup creation: {archive_name}")

    items_to_backup = [
        ("chroma_data", os.path.join(BASE_DIR, "chroma_data")),
        ("uploads", os.path.join(BASE_DIR, "uploads")),
        ("migrations", os.path.join(BASE_DIR, "migrations")),
    ]

    with tarfile.open(archive_path, "w:gz") as tar:
        for name, item_path in items_to_backup:
            if os.path.exists(item_path):
                print(f"  └── Archiving {name} ({item_path})...")
                tar.add(item_path, arcname=name)
            else:
                print(f"  └── Skipping {name} (directory does not exist)")

    size_mb = os.path.getsize(archive_path) / (1024 * 1024)
    print(f"✅ Backup created successfully: {archive_path} ({size_mb:.2f} MB)")
    return archive_path

if __name__ == "__main__":
    create_backup()
