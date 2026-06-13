"""Sdílené konstanty pro typy závodů.

Jediný zdroj pravdy pro barvu a zkratku každého typu závodu — používá ho
veřejný kalendář (event/views/views_public.py) i grafy účasti (rider/views.py),
aby barvy nedriftovaly mezi místy."""

from event.models_events import EventType

# Barva + zkratka pro každý typ závodu. Barva se používá pro odznak v kalendáři
# i jako barva série v grafech.
EVENT_TYPE_STYLES = {
    EventType.MCR_JEDNOTLIVCU: {"color": "#ef4444", "abbr": "MR"},
    EventType.MCR_DRUZSTEV: {"color": "#ef4444", "abbr": "MR"},
    EventType.CESKY_POHAR: {"color": "#3b82f6", "abbr": "ČP"},
    EventType.CESKA_LIGA: {"color": "#10b981", "abbr": "ČL"},
    EventType.MORAVSKA_LIGA: {"color": "#a16207", "abbr": "ML"},
    EventType.VOLNY_ZAVOD: {"color": "#f97316", "abbr": "VZ"},
    EventType.EVROPSKY_POHAR: {"color": "#8b5cf6", "abbr": "EP"},
    EventType.MISTROVSTVI_EVROPY: {"color": "#0891b2", "abbr": "ME"},
    EventType.MISTROVSTVI_SVETA: {"color": "#06b6d4", "abbr": "MS"},
    EventType.SVETOVY_POHAR: {"color": "#334155", "abbr": "WC"},
}

# Fallback pro neznámý / nebodovaný typ.
DEFAULT_EVENT_TYPE_STYLE = {"color": "#f97316", "abbr": "VZ"}


def event_type_color(event_type):
    """Barva pro daný typ závodu (s fallbackem)."""
    return EVENT_TYPE_STYLES.get(event_type, DEFAULT_EVENT_TYPE_STYLE)["color"]
