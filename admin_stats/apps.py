from django.apps import AppConfig


class AdminStatsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "admin_stats"

    def ready(self):
        from django.db.backends.signals import connection_created

        def _set_wal_mode(sender, connection, **kwargs):
            if connection.vendor == "sqlite":
                connection.cursor().execute("PRAGMA journal_mode=WAL;")
                connection.cursor().execute("PRAGMA synchronous=NORMAL;")

        connection_created.connect(_set_wal_mode)
