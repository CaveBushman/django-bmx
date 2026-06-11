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

## Produkční záloha (django-crontab) + offsite na Google Drive

Na produkci běží `bmx.cron.backup_sqlite_scheduled` přes `django-crontab` (viz
`CRONJOBS` v `bmx/settings.py`, denně ve 4:00). Tato úloha:

1. vytvoří konzistentní zálohu přes `sqlite3 .backup`,
2. zkomprimuje ji do `db.sqlite3.bak-YYYYMMDD-HHMMSS.gz`,
3. smaže lokální zálohy starší než posledních 7,
4. pokud je nastavena proměnná `OFFSITE_BACKUP_RCLONE_REMOTE`, nahraje
   zkomprimovanou zálohu na Google Drive přes `rclone copy` a smaže tamní
   zálohy starší než `OFFSITE_BACKUP_RETENTION_DAYS` dní (výchozí 30).

### Jednorázové nastavení rclone + Google Drive na serveru

1. Nainstaluj rclone na server:
   ```bash
   sudo -v && curl https://rclone.org/install.sh | sudo bash
   ```
2. Spusť `rclone authorize "drive"` na stroji **s prohlížečem** (např. na
   tomto Macu) — vypíše token:
   ```bash
   rclone authorize "drive"
   ```
3. Na serveru spusť `rclone config` (interaktivně) a vytvoř remote `gdrive`:
   - `n` (new remote) → name: `gdrive`
   - storage: `drive` (Google Drive)
   - client_id / client_secret: nech prázdné
   - scope: `drive` (plný přístup) nebo `drive.file` (jen soubory vytvořené
     aplikací)
   - "Use auto config?": **No** (server nemá prohlížeč)
   - vlož token z kroku 2
   - team drive: `No` (pokud nepoužíváš Shared Drive)
4. Ověř spojení a vytvoř cílovou složku:
   ```bash
   rclone mkdir gdrive:bmx-zalohy
   rclone lsd gdrive:
   ```
5. V produkčním `bmx/.env` nastav:
   ```bash
   OFFSITE_BACKUP_RCLONE_REMOTE=gdrive:bmx-zalohy
   OFFSITE_BACKUP_RETENTION_DAYS=30
   ```
6. Restartuj cron (`python manage.py crontab add`) nebo počkej na další
   spuštění ve 4:00 — výsledek se loguje (`SQLite backup: offsite upload OK`
   / `selhal`).
