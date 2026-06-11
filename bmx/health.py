import logging

from django.core.cache import cache
from django.db import connections


logger = logging.getLogger("ops.health")


def check_database():
    connection = connections["default"]
    connection.ensure_connection()
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
    if not row or row[0] != 1:
        raise RuntimeError("Database ping returned unexpected result.")
    return {"status": "ok"}


def check_cache():
    probe_key = "health:cache:probe"
    probe_value = "ok"
    cache.set(probe_key, probe_value, timeout=5)
    cached_value = cache.get(probe_key)
    if cached_value != probe_value:
        raise RuntimeError("Cache round-trip failed.")
    cache.delete(probe_key)
    return {"status": "ok"}


def check_celery():
    from django.conf import settings

    if settings.CELERY_TASK_ALWAYS_EAGER:
        return {"status": "ok", "mode": "eager"}

    from bmx.celery import app

    pings = app.control.inspect(timeout=1).ping()
    if not pings:
        raise RuntimeError("No Celery worker responded to ping.")
    return {"status": "ok", "workers": list(pings.keys())}


def collect_readiness_checks():
    checks = {}
    overall_status = "ok"

    for name, checker in (
        ("database", check_database),
        ("cache", check_cache),
        ("celery", check_celery),
    ):
        try:
            checks[name] = checker()
        except Exception as error:
            overall_status = "error"
            checks[name] = {
                "status": "error",
                "error": str(error),
            }
            logger.exception("Readiness check failed: %s", name)

    return {
        "status": overall_status,
        "checks": checks,
    }
