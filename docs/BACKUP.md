# Database backup

Projekt používá SQLite databázi v `db.sqlite3`.

## Ruční spuštění

```bash
./scripts/backup_sqlite.sh
```

Výstup:
- záloha se uloží do `backups/db/`
- formát souboru: `db-YYYYMMDD-HHMMSS.sqlite3.gz`
- starší zálohy se mažou po `14` dnech

## Volitelné proměnné

```bash
RETENTION_DAYS=30 ./scripts/backup_sqlite.sh
BACKUP_DIR=/path/to/backups ./scripts/backup_sqlite.sh
DB_PATH=/path/to/db.sqlite3 ./scripts/backup_sqlite.sh
```

## Automatizace přes cron

Každou noc ve `02:15`:

```cron
15 2 * * * cd /Users/david/Library/Mobile\ Documents/com~apple~CloudDocs/Development/BMX\ website/django-bmx && /bin/zsh ./scripts/backup_sqlite.sh >> logs/backup.log 2>&1
```

## Poznámka

Script používá `sqlite3 .backup`, takže je bezpečnější než prosté `cp db.sqlite3` nad běžící aplikací.
