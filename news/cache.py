from datetime import date

from django.core.cache import cache


def homepage_data_cache_key(day=None):
    day = day or date.today()
    return f"homepage:view-data:{day.year}:{day.isoformat()}"


def invalidate_homepage_data_cache():
    """Odstraní dnešní datovou cache homepage."""
    cache.delete(homepage_data_cache_key())
