from django.core.cache import cache


def get_client_ip(request):
    """Skutečná IP klienta za reverzní proxy (nginx).

    Gunicorn běží za nginxem, takže REMOTE_ADDR je u všech požadavků stejná
    a limity by platily pro celý web najednou. Bereme poslední položku
    X-Forwarded-For – tu přidává náš nginx a klient ji nemůže podvrhnout.
    """
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        last_hop = forwarded_for.split(",")[-1].strip()
        if last_hop:
            return last_hop
    return request.META.get("REMOTE_ADDR") or "unknown"


def get_rate_limit_subject(request, *, scope_to_user=False):
    remote_addr = get_client_ip(request)
    if scope_to_user and getattr(request, "user", None) is not None and request.user.is_authenticated:
        return f"user:{request.user.pk}:{remote_addr}"
    return f"ip:{remote_addr}"


def is_rate_limited(scope, subject, *, window_seconds, max_attempts):
    cache_key = f"rate-limit:{scope}:{subject}"
    attempts = cache.get(cache_key, 0) + 1
    cache.set(cache_key, attempts, window_seconds)
    return attempts > max_attempts, attempts
