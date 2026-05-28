from .celery import app as celery_app

__all__ = ("celery_app",)

from django.db.backends.signals import connection_created


def _set_sqlite_wal(sender, connection, **kwargs):
    if connection.vendor == "sqlite":
        connection.cursor().execute("PRAGMA journal_mode=WAL;")
        connection.cursor().execute("PRAGMA synchronous=NORMAL;")


connection_created.connect(_set_sqlite_wal)
