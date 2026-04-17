import copy
from contextlib import nullcontext
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

try:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
except ImportError:  # pragma: no cover - optional dependency in local dev
    sentry_sdk = None
    DjangoIntegration = None
    LoggingIntegration = None


SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-csrftoken",
    "x-csr-token",
    "stripe-signature",
}
SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "card",
    "cookie",
    "csrfmiddlewaretoken",
    "password",
    "passwd",
    "secret",
    "session",
    "signature",
    "token",
}
SENTRY_HEALTHCHECK_PATHS = {"/healthz", "/readyz", "/csp-report"}


def _is_sensitive_key(key):
    normalized = str(key).strip().lower().replace("-", "_")
    return any(fragment in normalized for fragment in SENSITIVE_KEYS)


def _sanitize_mapping(mapping, *, redact_all_values=False):
    sanitized = {}
    for key, value in (mapping or {}).items():
        if redact_all_values or _is_sensitive_key(key):
            sanitized[key] = "[Filtered]"
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_mapping(value)
        elif isinstance(value, list):
            sanitized[key] = [
                _sanitize_mapping(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value
    return sanitized


def _sanitize_url(url):
    if not url:
        return url

    parsed_url = urlsplit(str(url))
    if not parsed_url.query:
        return str(url)

    sanitized_query = []
    for key, value in parse_qsl(parsed_url.query, keep_blank_values=True):
        sanitized_query.append((key, "[Filtered]" if _is_sensitive_key(key) else value))

    return urlunsplit(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            urlencode(sanitized_query, doseq=True),
            parsed_url.fragment,
        )
    )


def _normalize_healthcheck_path(raw_value):
    value = str(raw_value or "").strip().lower()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        value = urlsplit(value).path
    if not value.startswith("/"):
        value = f"/{value}"
    return value.rstrip("/") or "/"


def _is_healthcheck_path(raw_value, healthcheck_paths):
    return _normalize_healthcheck_path(raw_value) in healthcheck_paths


def _coerce_sample_rate(value, default):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(value, 0.0), 1.0)


def _resolve_release(release, release_candidates):
    if release:
        return release

    for candidate in release_candidates:
        if candidate:
            return str(candidate).strip()
    return ""


def scrub_sentry_event(event, hint=None):
    scrubbed_event = copy.deepcopy(event)
    request_data = scrubbed_event.get("request") or {}
    headers = request_data.get("headers") or {}
    sanitized_headers = {}

    for key, value in headers.items():
        normalized = str(key).strip().lower()
        sanitized_headers[key] = "[Filtered]" if normalized in SENSITIVE_HEADERS else value

    if sanitized_headers:
        request_data["headers"] = sanitized_headers

    if "data" in request_data:
        request_data["data"] = (
            _sanitize_mapping(request_data["data"])
            if isinstance(request_data["data"], dict)
            else "[Filtered]"
        )
    if "cookies" in request_data:
        request_data["cookies"] = "[Filtered]"
    if "env" in request_data and isinstance(request_data["env"], dict):
        request_data["env"] = _sanitize_mapping(request_data["env"])
    if request_data.get("url"):
        request_data["url"] = _sanitize_url(request_data["url"])

    scrubbed_event["request"] = request_data

    for container_name in ("extra", "contexts", "tags"):
        container = scrubbed_event.get(container_name)
        if isinstance(container, dict):
            scrubbed_event[container_name] = _sanitize_mapping(container)

    user_data = scrubbed_event.get("user")
    if isinstance(user_data, dict):
        scrubbed_event["user"] = {
            key: value
            for key, value in user_data.items()
            if str(key).lower() not in {"email", "ip_address", "username"}
        }

    return scrubbed_event


def sentry_traces_sampler(sampling_context, *, traces_sample_rate, healthcheck_paths=None):
    normalized_healthcheck_paths = healthcheck_paths or SENTRY_HEALTHCHECK_PATHS
    transaction_context = sampling_context.get("transaction_context") or {}
    transaction_name = transaction_context.get("name")
    wsgi_environ = sampling_context.get("wsgi_environ") or {}
    asgi_scope = sampling_context.get("asgi_scope") or {}
    request = sampling_context.get("request")

    candidate_paths = [
        transaction_name,
        wsgi_environ.get("PATH_INFO"),
        asgi_scope.get("path"),
        getattr(request, "path", ""),
    ]
    if any(_is_healthcheck_path(path, normalized_healthcheck_paths) for path in candidate_paths):
        return 0.0
    return _coerce_sample_rate(traces_sample_rate, 0.0)


def before_send_transaction(event, hint=None, *, healthcheck_paths=None):
    normalized_healthcheck_paths = healthcheck_paths or SENTRY_HEALTHCHECK_PATHS
    request_data = event.get("request") or {}
    url = request_data.get("url")
    transaction_name = event.get("transaction")

    if _is_healthcheck_path(url, normalized_healthcheck_paths) or _is_healthcheck_path(
        transaction_name, normalized_healthcheck_paths
    ):
        return None
    return event


def before_breadcrumb(crumb, hint=None, *, healthcheck_paths=None):
    normalized_healthcheck_paths = healthcheck_paths or SENTRY_HEALTHCHECK_PATHS
    category = str(crumb.get("category") or "").lower()
    if category.startswith("http") or category.startswith("django"):
        crumb_data = crumb.get("data") or {}
        url = crumb_data.get("url") or crumb_data.get("path")
        if _is_healthcheck_path(url, normalized_healthcheck_paths):
            return None
        if isinstance(crumb_data.get("headers"), dict):
            crumb_data = dict(crumb_data)
            crumb_data["headers"] = _sanitize_mapping(
                crumb_data["headers"],
                redact_all_values=False,
            )
            crumb["data"] = crumb_data
    return crumb


def initialize_sentry(
    *,
    dsn,
    enabled,
    environment,
    release="",
    release_candidates=(),
    traces_sample_rate=0.0,
    profiles_sample_rate=0.0,
    send_default_pii=False,
    max_breadcrumbs=50,
    log_level=None,
    event_level=None,
    healthcheck_paths=None,
    debug=False,
    stripe_live_mode=False,
):
    if sentry_sdk is None or not enabled or not dsn:
        return False

    normalized_healthcheck_paths = {
        _normalize_healthcheck_path(path)
        for path in (healthcheck_paths or SENTRY_HEALTHCHECK_PATHS)
        if _normalize_healthcheck_path(path)
    } or SENTRY_HEALTHCHECK_PATHS

    integrations = []
    if DjangoIntegration is not None:
        integrations.append(DjangoIntegration())
    if LoggingIntegration is not None:
        integrations.append(LoggingIntegration(level=log_level, event_level=event_level))

    sentry_init_kwargs = {
        "dsn": dsn,
        "environment": environment,
        "send_default_pii": send_default_pii,
        "max_request_body_size": "never",
        "max_breadcrumbs": max_breadcrumbs,
        "traces_sampler": lambda sampling_context: sentry_traces_sampler(
            sampling_context,
            traces_sample_rate=traces_sample_rate,
            healthcheck_paths=normalized_healthcheck_paths,
        ),
        "profiles_sample_rate": _coerce_sample_rate(profiles_sample_rate, 0.0),
        "before_send": scrub_sentry_event,
        "before_send_transaction": lambda event, hint: before_send_transaction(
            event,
            hint,
            healthcheck_paths=normalized_healthcheck_paths,
        ),
        "before_breadcrumb": lambda crumb, hint: before_breadcrumb(
            crumb,
            hint,
            healthcheck_paths=normalized_healthcheck_paths,
        ),
        "integrations": integrations,
    }

    resolved_release = _resolve_release(release, release_candidates)
    if resolved_release:
        sentry_init_kwargs["release"] = resolved_release

    sentry_sdk.init(**sentry_init_kwargs)
    with sentry_sdk.configure_scope() as scope:
        scope.set_tag("app", "django-bmx")
        scope.set_tag("django.debug", debug)
        scope.set_tag("stripe.live_mode", stripe_live_mode)
    return True


def start_span(*, op, name, **attributes):
    if sentry_sdk is None:
        return nullcontext()

    span = sentry_sdk.start_span(op=op, name=name)
    for key, value in attributes.items():
        if value is not None:
            span.set_data(key, value)
    return span


def set_tag(key, value):
    if sentry_sdk is None or value is None:
        return
    sentry_sdk.set_tag(key, value)
