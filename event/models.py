"""Veřejná fasáda modelů aplikace ``event``.

Modely jsou kvůli velikosti domény rozdělené do ``models_events``,
``models_entries``, ``models_results`` a ``models_finance``. Ostatní kód má
importovat z ``event.models``, aby fyzické rozdělení zůstalo implementační detail.
"""

from event.models_entries import Entry, EntryAuditLog, EntryForeign
from event.models_events import EntryClasses, Event, EventPhoto, EventProposition, EventType, SeasonSettings
from event.models_finance import CreditTransaction, DebetTransaction, FinanceAuditLog, StripeFee
from event.models_results import RaceRun, Result
from event.utils import normalize_uci_id

__all__ = [
    "CreditTransaction",
    "DebetTransaction",
    "Entry",
    "EntryAuditLog",
    "EntryClasses",
    "EntryForeign",
    "Event",
    "EventPhoto",
    "EventProposition",
    "EventType",
    "FinanceAuditLog",
    "RaceRun",
    "Result",
    "SeasonSettings",
    "StripeFee",
    "normalize_uci_id",
]
