#!/bin/zsh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DB_PATH="${DB_PATH:-$PROJECT_DIR/db.sqlite3}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups/db}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"
TMP_PATH="$BACKUP_DIR/db-$TIMESTAMP.sqlite3"
ARCHIVE_PATH="$TMP_PATH.gz"

if [[ ! -f "$DB_PATH" ]]; then
  echo "Database file not found: $DB_PATH" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

# Use SQLite's native online backup to avoid copying an inconsistent live file.
/usr/bin/sqlite3 "$DB_PATH" ".backup '$TMP_PATH'"
/usr/bin/gzip -f "$TMP_PATH"

# Keep only recent compressed backups.
/usr/bin/find "$BACKUP_DIR" -type f -name 'db-*.sqlite3.gz' -mtime +"$RETENTION_DAYS" -delete

echo "Backup created: $ARCHIVE_PATH"
