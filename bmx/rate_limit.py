from django.core.cache import cache


def get_rate_limit_subject(request, *, scope_to_user=False):
    remote_addr = request.META.get("REMOTE_ADDR", "unknown")
    if scope_to_user and getattr(request, "user", None) is not None and request.user.is_authenticated:
        return f"user:{request.user.pk}:{remote_addr}"
    return f"ip:{remote_addr}"


def is_rate_limited(scope, subject, *, window_seconds, max_attempts):
    cache_key = f"rate-limit:{scope}:{subject}"
    attempts = cache.get(cache_key, 0) + 1
    cache.set(cache_key, attempts, window_seconds)
    return attempts > max_attempts, attempts
