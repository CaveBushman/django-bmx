import logging
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


def backup_sqlite_scheduled():
    """Záloha SQLite databáze pomocí .backup příkazu (konzistentní kopie za běhu)."""
    db_path = Path(settings.DATABASES["default"]["NAME"])
    if not db_path.exists():
        logger.error("SQLite backup: databáze nenalezena na %s", db_path)
        return

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_name(f"db.sqlite3.bak-{stamp}")

    try:
        result = subprocess.run(
            ["sqlite3", str(db_path), f".backup {backup_path}"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            size_mb = backup_path.stat().st_size / 1024 / 1024
            logger.info("SQLite backup OK → %s (%.1f MB)", backup_path.name, size_mb)
            _prune_old_backups(db_path.parent, keep=7)
        else:
            logger.error("SQLite backup selhal: %s", result.stderr)
    except Exception:
        logger.exception("SQLite backup: neočekávaná chyba")


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


def _prune_old_backups(directory: Path, keep: int = 7):
    backups = sorted(directory.glob("db.sqlite3.bak-*"))
    for old in backups[:-keep]:
        try:
            old.unlink()
            logger.info("SQLite backup smazán (prune): %s", old.name)
        except Exception:
            logger.warning("SQLite backup nelze smazat: %s", old.name)


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
