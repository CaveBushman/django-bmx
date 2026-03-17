"""
event/views/views_public.py — veřejné pohledy (bez přihlášení)

Obsah: seznam závodů, detail závodu, výsledky, ranking tabulka, not-reg stránka.
"""

import logging
from datetime import date
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from event.models import Event, EventProposition, Result, SeasonSettings, Entry, EntryForeign
from event.views.views_proposition import can_manage_event_proposition
from event.func import is_registration_open

logger = logging.getLogger(__name__)


EVENT_LIST_RELATED = ("organizer", "classes_and_fees_like", "structured_proposition")


def _get_structured_proposition(event):
    try:
        return event.structured_proposition
    except EventProposition.DoesNotExist:
        return None


def _events_for_year(year):
    return (
        Event.objects.filter(date__year=year)
        .select_related(*EVENT_LIST_RELATED)
        .only(
            "id",
            "name",
            "date",
            "type_for_ranking",
            "reg_open",
            "reg_open_from",
            "reg_open_to",
            "canceled",
            "uec_link",
            "youtube_link",
            "proposition",
            "html_results",
            "series",
            "structured_proposition__is_published",
            "organizer__team_name",
            "classes_and_fees_like__event_name",
        )
        .order_by("date")
    )


def _decorate_events(events):
    decorated = []
    for event in events:
        classes_config = getattr(event, "classes_and_fees_like", None)
        has_configured_classes = bool(
            classes_config and classes_config.event_name != "Dosud nenastaveno"
        )
        event.reg_open = (
            not event.canceled
            and has_configured_classes
            and is_registration_open(event)
        )
        proposition = _get_structured_proposition(event)
        event.has_public_proposition = bool(proposition and proposition.is_published)
        decorated.append(event)
    return decorated


def events_list_view(request):
    """Seznam závodů aktuálního roku — nadcházející a proběhlé."""
    year = date.today().year
    today = date.today()
    all_events = list(_events_for_year(year))
    upcomming_events = _decorate_events(
        [event for event in all_events if event.date and event.date >= today]
    )
    past_events = [event for event in all_events if event.date and event.date < today]

    data = {
        "events": upcomming_events,
        "past_events": past_events,
        "year": year,
        "next_year": int(year) + 1,
        "last_year": int(year) - 1,
        "show_title": True,
        "hero_description": f"Přehled plánovaných závodů, otevřených registrací a archivních termínů pro sezonu {year}.",
        "upcoming_label": "Následující závody",
        "archive_label": "Ukončené závody",
        "season_label": "Nejbližší závody",
        "archive_heading": "Ukončené závody",
        "season_context": "Archiv",
    }
    return render(request, "event/events-list_new.html", data)


def events_list_by_year_view(request, pk):
    """Seznam závodů zvoleného roku (archiv)."""
    if pk == date.today().year:
        return redirect('event:events')

    all_events = list(_events_for_year(pk))
    today = date.today()
    upcoming_events = _decorate_events(
        [event for event in all_events if event.date and event.date >= today]
    )
    past_events = [event for event in all_events if event.date and event.date < today]

    if pk < today.year:
        hero_description = f"Přehled archivních závodů a uzavřených termínů pro sezonu {pk}."
        upcoming_label = "Budoucí závody"
        archive_label = "Odjeté závody"
        archive_heading = f"Archiv {pk}"
        season_context = "Archiv"
    else:
        hero_description = f"Přehled plánovaných závodů a budoucích termínů pro sezonu {pk}."
        upcoming_label = "Plánované závody"
        archive_label = "Odjeté závody"
        archive_heading = f"Sezona {pk}"
        season_context = "Sezona"

    data = {
        "events": upcoming_events,
        "past_events": past_events,
        "year": pk,
        "next_year": int(pk) + 1,
        "last_year": int(pk) - 1,
        "show_title": False,
        "hero_description": hero_description,
        "upcoming_label": upcoming_label,
        "archive_label": archive_label,
        "season_label": archive_heading,
        "archive_heading": archive_heading,
        "season_context": season_context,
    }
    return render(request, "event/events-list_new.html", data)


def event_detail_views(request, pk):
    """Detail závodu — info, datum, místo, stav registrace."""
    event = get_object_or_404(
        Event.objects.select_related("organizer", "structured_proposition"),
        pk=pk,
    )
    reg_open = is_registration_open(event)
    proposition = _get_structured_proposition(event)
    riders_sum = Entry.objects.filter(event=pk, payment_complete=True, checkout=False).count()
    riders_sum += EntryForeign.objects.filter(event=pk, payment_complete=True, checkout=False).count()
    data = {
        "event": event,
        "alert": False,
        "select_category": "",
        "riders_sum": riders_sum,
        "reg_open": reg_open,
        "has_public_proposition": bool(proposition and proposition.is_published),
        "public_proposition": proposition if proposition and proposition.is_published else None,
        "can_edit_proposition": can_manage_event_proposition(request.user, event),
    }
    return render(request, "event/event-detail.html", data)


def results_view(request, pk):
    """Výsledky závodu — tabulka s pořadím jezdců."""
    event = get_object_or_404(Event, pk=pk)
    results = Result.objects.filter(event=pk).order_by("category", "place")
    data = {"results": results, "event": event}
    return render(request, "event/results.html", data)


def ranking_table_view(request):
    """Tabulka rankingových bodů — zatím prázdná stránka."""
    return render(request, "event/ranking-table.html", {})


def not_reg_view(request):
    """Stránka pro nepřihlášené uživatele (redirect z @login_required)."""
    return render(request, "event/not-reg.html", {})
