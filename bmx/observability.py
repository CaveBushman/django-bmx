from contextlib import nullcontext

try:
    import sentry_sdk
except ImportError:  # pragma: no cover - optional dependency in local dev
    sentry_sdk = None


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
