"""Přechod na BIKODY.COM (BMX Event Control).

Od ``settings.WEB_REGISTRATION_END_DATE`` (výchozí 1. 1. 2027) se na závody
přihlašuje a prémiové statistiky jezdců předplácí na bikody.com. Web pak:

- nenabízí přihlášku na závody konané od tohoto dne (``can_register``),
- nepřijímá nové předplatné prémiových statistik ani ho neobnovuje —
  běžící období předplatného nechá doběhnout.

Kredity se ruší: po ``settings.CREDIT_TOPUP_LAST_DATE`` (výchozí 30. 10. 2026)
už nejde kredit dobít a nevyčerpané zůstatky se uživatelům vrací.
"""

from datetime import date, datetime

from django.conf import settings
from django.utils import timezone


def switch_date() -> date:
    return date.fromisoformat(settings.WEB_REGISTRATION_END_DATE)


def bikody_url() -> str:
    return settings.BIKODY_URL


def is_event_registered_on_bikody(event) -> bool:
    """Přihlášky na závod konaný od data přechodu přijímá jen bikody.com."""
    return bool(getattr(event, "date", None)) and event.date >= switch_date()


def is_after_switch(at_time=None) -> bool:
    """Je už po přechodu (web nemá prodávat ani obnovovat předplatné)?"""
    moment = at_time or timezone.now()
    local_day = timezone.localdate(moment) if isinstance(moment, datetime) else moment
    return local_day >= switch_date()


def credit_topup_last_date() -> date:
    return date.fromisoformat(settings.CREDIT_TOPUP_LAST_DATE)


def is_credit_topup_open(at_time=None) -> bool:
    """Lze ještě dobít kredit? Poslední den dobíjení je ``CREDIT_TOPUP_LAST_DATE``."""
    moment = at_time or timezone.now()
    local_day = timezone.localdate(moment) if isinstance(moment, datetime) else moment
    return local_day <= credit_topup_last_date()


CREDIT_TOPUP_CLOSED_MESSAGE = "Dobíjení kreditu bylo ukončeno. Nevyčerpaný kredit vám vrátíme."
