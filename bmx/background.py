"""Pomocné funkce pro rozhodování o způsobu běhu úloh na pozadí.

Projekt podporuje dva režimy zpracování přepočtů:

* **Celery** — když je nakonfigurovaný reálný broker (REDIS_URL v produkci).
  Úloha běží v samostatném workeru, přežije restart/deploy webu a má retry.
* **Daemon vlákno** — fallback pro vývoj bez Redisu, kdy je Celery v režimu
  ALWAYS_EAGER (tam by `.delay()` běžel synchronně a blokoval request).
"""

from django.conf import settings


def should_use_celery():
    """True, pokud se má úloha poslat do Celery workeru (reálný broker).
    False ve vývoji bez brokeru (ALWAYS_EAGER) → použij vlákno."""
    return not getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)
