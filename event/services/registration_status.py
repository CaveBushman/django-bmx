from django.utils import timezone


def get_registration_deadline(event):
    return getattr(event, "reg_open_to", None)


def get_unregistration_deadline(event):
    return getattr(event, "reg_cancel_to", None) or get_registration_deadline(event)


def _is_event_registration_enabled(event):
    return not event.xls_results and bool(event.reg_open)


def can_register(event) -> bool:
    if not _is_event_registration_enabled(event):
        return False

    now = timezone.now()
    registration_from = getattr(event, "reg_open_from", None)
    registration_to = get_registration_deadline(event)

    try:
        return registration_from <= now <= registration_to
    except (TypeError, AttributeError):
        return False


def can_unregister(event) -> bool:
    if not _is_event_registration_enabled(event):
        return False

    deadline = get_unregistration_deadline(event)
    if deadline is None:
        return False

    try:
        return timezone.now() <= deadline
    except TypeError:
        return False
