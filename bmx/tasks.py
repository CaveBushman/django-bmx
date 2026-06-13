"""Celery tasky pro periodické úlohy (alternativa k django-crontab přes Celery beat).

Tenké obaly nad funkcemi v bmx.cron — tatáž logika běží buď přes systémový
cron (django-crontab), nebo přes Celery beat, podle settings.USE_CELERY_BEAT.
Naplánování je v settings.CELERY_BEAT_SCHEDULE."""

from celery import shared_task

from bmx import cron


@shared_task(name="bmx.valid_licence")
def valid_licence_task():
    return cron.valid_licence_scheduled()


@shared_task(name="bmx.renew_rider_stats_subscriptions")
def renew_rider_stats_subscriptions_task():
    return cron.renew_rider_stats_subscriptions_scheduled()


@shared_task(name="bmx.renew_trainer_club_subscriptions")
def renew_trainer_club_subscriptions_task():
    return cron.renew_trainer_club_subscriptions_scheduled()


@shared_task(name="bmx.renew_mobile_app_subscriptions")
def renew_mobile_app_subscriptions_task():
    return cron.renew_mobile_app_subscriptions_scheduled()


@shared_task(name="bmx.backup_database")
def backup_database_task():
    return cron.backup_database_scheduled()


@shared_task(name="bmx.check_sqlite_integrity")
def check_sqlite_integrity_task():
    return cron.check_sqlite_integrity_scheduled()


@shared_task(name="bmx.prune_old_visits")
def prune_old_visits_task():
    return cron.prune_old_visits_scheduled()


@shared_task(name="bmx.optimize_sqlite")
def optimize_sqlite_task():
    return cron.optimize_sqlite_scheduled()


@shared_task(name="bmx.check_entry_integrity")
def check_entry_integrity_task():
    return cron.check_entry_integrity_scheduled()


@shared_task(name="bmx.run_ai_agent")
def run_ai_agent_task():
    from django.core.management import call_command
    return call_command("run_ai_agent")
