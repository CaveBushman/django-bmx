import gzip
import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings

from rider.rider import refresh_valid_licences
from rider.subscriptions import renew_due_rider_stats_subscriptions, renew_due_trainer_club_subscriptions
from rider.mobile_subscriptions import renew_due_mobile_app_subscriptions

logger = logging.getLogger(__name__)


def valid_licence_scheduled():
    """Spustí pravidelnou kontrolu platnosti licencí."""
    return refresh_valid_licences()


def renew_rider_stats_subscriptions_scheduled():
    """Obnoví expirovaná předplatná prémiových statistik jezdců."""
    return renew_due_rider_stats_subscriptions()


def renew_trainer_club_subscriptions_scheduled():
    """Obnoví expirovaná trenérská klubová předplatná."""
    return renew_due_trainer_club_subscriptions()


def renew_mobile_app_subscriptions_scheduled():
    """Obnoví expirovaná předplatná mobilní aplikace."""
    return renew_due_mobile_app_subscriptions()


def backup_database_scheduled():
    """Spustí zálohu podle aktuálně nakonfigurovaného DB enginu (SQLite nebo PostgreSQL)."""
    engine = settings.DATABASES["default"]["ENGINE"]
    if engine == "django.db.backends.sqlite3":
        return backup_sqlite_scheduled()
    if engine == "django.db.backends.postgresql":
        return backup_postgres_scheduled()
    logger.error("Záloha DB: nepodporovaný DB engine %s", engine)


def backup_sqlite_scheduled():
    """Záloha SQLite databáze pomocí .backup příkazu (konzistentní kopie za běhu),
    komprese gzip a kopie do offsite úložiště (Google Drive přes rclone), pokud je nastavené."""
    db_path = Path(settings.DATABASES["default"]["NAME"])
    if not db_path.exists():
        logger.error("SQLite backup: databáze nenalezena na %s", db_path)
        return

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_name(f"db.sqlite3.bak-{stamp}")

    try:
        # Online záloha přes vestavěné sqlite3 (konzistentní kopie za běhu).
        # Dříve volalo `sqlite3` CLI, které ale v produkčním image (python:3.13-slim)
        # ani v CI není nainstalované → záloha tiše selhávala.
        import sqlite3 as _sqlite3

        source_conn = _sqlite3.connect(str(db_path), timeout=300)
        dest_conn = _sqlite3.connect(str(backup_path))
        try:
            with dest_conn:
                source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
            source_conn.close()

        gz_path = _gzip_backup(backup_path)
        size_mb = gz_path.stat().st_size / 1024 / 1024
        logger.info("SQLite backup OK → %s (%.1f MB)", gz_path.name, size_mb)

        _prune_old_backups(db_path.parent, "db.sqlite3.bak-*", keep=7)
        _upload_backup_offsite(gz_path)
    except Exception:
        logger.exception("SQLite backup: neočekávaná chyba")


def backup_postgres_scheduled():
    """Záloha PostgreSQL databáze pomocí pg_dump, komprese gzip a kopie do
    offsite úložiště (Google Drive přes rclone), pokud je nastavené.

    Připraveno pro budoucí migraci z SQLite na PostgreSQL — stačí v
    DATABASES['default']['ENGINE'] nastavit 'django.db.backends.postgresql'
    a mít na serveru dostupný binárku pg_dump."""
    db = settings.DATABASES["default"]
    db_name = db["NAME"]
    backup_dir = Path(settings.BASE_DIR)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    pattern = f"db-{db_name}.bak-*"
    dump_path = backup_dir / f"db-{db_name}.bak-{stamp}.sql"

    cmd = ["pg_dump", "--no-owner", "--format=plain", "--file", str(dump_path), db_name]
    if db.get("USER"):
        cmd += ["--username", db["USER"]]
    if db.get("HOST"):
        cmd += ["--host", db["HOST"]]
    if db.get("PORT"):
        cmd += ["--port", str(db["PORT"])]

    env = os.environ.copy()
    if db.get("PASSWORD"):
        env["PGPASSWORD"] = db["PASSWORD"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,
            env=env,
        )
        if result.returncode != 0:
            logger.error("PostgreSQL backup selhal: %s", result.stderr)
            return

        gz_path = _gzip_backup(dump_path)
        size_mb = gz_path.stat().st_size / 1024 / 1024
        logger.info("PostgreSQL backup OK → %s (%.1f MB)", gz_path.name, size_mb)

        _prune_old_backups(backup_dir, pattern, keep=7)
        _upload_backup_offsite(gz_path)
    except FileNotFoundError:
        logger.error("PostgreSQL backup: pg_dump není nainstalován")
    except Exception:
        logger.exception("PostgreSQL backup: neočekávaná chyba")


def _gzip_backup(backup_path: Path) -> Path:
    """Zkomprimuje záložní soubor do .gz a originál smaže."""
    gz_path = backup_path.with_name(backup_path.name + ".gz")
    with open(backup_path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    backup_path.unlink()
    return gz_path


def _upload_backup_offsite(backup_path: Path):
    """Nahraje zazipovanou zálohu na Google Drive přes rclone (pokud je remote nastaven)."""
    remote = settings.OFFSITE_BACKUP_RCLONE_REMOTE
    if not remote:
        return

    try:
        result = subprocess.run(
            ["rclone", "copy", str(backup_path), remote, "--quiet"],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode == 0:
            logger.info("SQLite backup: offsite upload OK → %s", remote)
            _prune_offsite_backups(remote)
        else:
            logger.error("SQLite backup: offsite upload selhal: %s", result.stderr)
    except FileNotFoundError:
        logger.error("SQLite backup: rclone není nainstalován, offsite upload přeskočen")
    except Exception:
        logger.exception("SQLite backup: offsite upload neočekávaná chyba")


def _prune_offsite_backups(remote: str):
    """Smaže offsite zálohy starší než OFFSITE_BACKUP_RETENTION_DAYS dní."""
    keep_days = settings.OFFSITE_BACKUP_RETENTION_DAYS
    try:
        result = subprocess.run(
            ["rclone", "delete", remote, "--min-age", f"{keep_days}d", "--quiet"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            logger.warning("SQLite backup: prune offsite záloh selhal: %s", result.stderr)
    except Exception:
        logger.exception("SQLite backup: prune offsite záloh neočekávaná chyba")


def prune_old_visits_scheduled():
    """Smaže Visit záznamy starší než 1 rok a uvolní místo na disku přes VACUUM."""
    import sqlite3 as _sqlite3
    from datetime import timedelta
    from django.utils import timezone
    from admin_stats.models import Visit

    cutoff = timezone.now() - timedelta(days=365)
    try:
        deleted, _ = Visit.objects.filter(timestamp__lt=cutoff).delete()
        logger.info("Visit prune: smazáno %d záznamů starších než %s", deleted, cutoff.date())
    except Exception:
        logger.exception("Visit prune: neočekávaná chyba")
        return

    if deleted == 0:
        return

    db_path = Path(settings.DATABASES["default"]["NAME"])
    try:
        conn = _sqlite3.connect(str(db_path), timeout=60)
        conn.execute("VACUUM;")
        conn.close()
        logger.info("Visit prune: VACUUM dokončen")
    except Exception:
        logger.exception("Visit prune: VACUUM selhal")


def _prune_old_backups(directory: Path, pattern: str, keep: int = 7):
    backups = sorted(directory.glob(pattern))
    for old in backups[:-keep]:
        try:
            old.unlink()
            logger.info("Záloha smazána (prune): %s", old.name)
        except Exception:
            logger.warning("Zálohu nelze smazat: %s", old.name)


def check_sqlite_integrity_scheduled():
    """Týdenní kontrola integrity SQLite databáze. Při nálezu chyb pošle e-mail."""
    import sqlite3 as _sqlite3

    db_path = Path(settings.DATABASES["default"]["NAME"])
    if not db_path.exists():
        logger.error("SQLite integrity check: databáze nenalezena na %s", db_path)
        return

    try:
        conn = _sqlite3.connect(str(db_path), timeout=30)
        rows = conn.execute("PRAGMA integrity_check(100);").fetchall()
        conn.close()
    except Exception:
        logger.exception("SQLite integrity check: chyba při připojení k DB")
        return

    results = [row[0] for row in rows]
    if results == ["ok"]:
        logger.info("SQLite integrity check: OK")
        return

    message = "\n".join(results)
    logger.error("SQLite integrity check SELHALA:\n%s", message)

    recipients = [e.strip() for e in settings.AI_AGENT_NOTIFY_EMAILS if e.strip()]
    if recipients:
        from django.core.mail import send_mail
        try:
            send_mail(
                subject="[CzechBMX] SQLite integrity check SELHALA",
                message=f"Databáze {db_path} hlásí chyby integrity:\n\n{message}\n\nZálohuj a oprav DB co nejdříve.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipients,
                fail_silently=True,
            )
        except Exception:
            logger.exception("SQLite integrity check: nepodařilo se odeslat e-mail")


def optimize_sqlite_scheduled():
    """Denní PRAGMA optimize — aktualizuje statistiky query planneru pro lepší výběr indexů."""
    import sqlite3 as _sqlite3

    db_path = Path(settings.DATABASES["default"]["NAME"])
    if not db_path.exists():
        return

    try:
        conn = _sqlite3.connect(str(db_path), timeout=30)
        conn.execute("PRAGMA optimize;")
        conn.close()
        logger.info("SQLite optimize: OK")
    except Exception:
        logger.exception("SQLite optimize: neočekávaná chyba")


def check_entry_integrity_scheduled():
    """Najde osiřelé reference Entry.rider / Result.rider (db_constraint=False).
    Pouze report — záznamy nevynuluje. E-mail pošle jen při osiřelých Entry
    (skutečný viselec); osiřelé Result jsou obvykle zahraniční jezdci, ty
    se jen zalogují, aby týdenní běh nespamoval."""
    import re
    from io import StringIO
    from django.core.management import call_command

    out = StringIO()
    try:
        call_command("check_entry_integrity", stdout=out, stderr=out)
    except Exception:
        logger.exception("Entry integrity check: neočekávaná chyba")
        return

    report = out.getvalue()
    logger.info("Entry integrity check:\n%s", report)

    # Alert jen pokud existují osiřelé Entry (akční problém).
    if not re.search(r"Entry: \d+ osiřelých", report):
        return

    logger.error("Entry integrity check nalezl osiřelé Entry:\n%s", report)

    recipients = [e.strip() for e in settings.AI_AGENT_NOTIFY_EMAILS if e.strip()]
    if recipients:
        from django.core.mail import send_mail
        try:
            send_mail(
                subject="[CzechBMX] Nalezeny osiřelé registrace (Entry.rider)",
                message=f"Kontrola integrity našla osiřelé Entry záznamy:\n\n{report}\n\n"
                        f"Pro vynulování spusť: python manage.py check_entry_integrity --fix",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipients,
                fail_silently=True,
            )
        except Exception:
            logger.exception("Entry integrity check: nepodařilo se odeslat e-mail")
