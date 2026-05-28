import os
from pathlib import Path
from datetime import date

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum, Count, F, Q
from django.conf import settings
from django.http import FileResponse, Http404
from django.shortcuts import render, get_object_or_404

from .models import Club
from rider.models import Rider
from event.models import Event, Entry
from .func import riders_on_events
# import folium


# Create your views here.

def clubs_list_view(request):
    base_clubs = (
        Club.objects.filter(is_active=True)
        .exclude(team_name="Bez klubové příslušnosti")
        .order_by("team_name")
    )
    query = (request.GET.get("q") or "").strip()
    selected_region = (request.GET.get("region") or "").strip()

    clubs = base_clubs
    if query:
        clubs = clubs.filter(
            Q(team_name__icontains=query)
            | Q(contact_person__icontains=query)
            | Q(contact_email__icontains=query)
            | Q(city__icontains=query)
        )
    if selected_region:
        clubs = clubs.filter(region=selected_region)

    cleaned_clubs = []
    for club in clubs:
        contact_person = "" if club.contact_person in {"", "nan"} else club.contact_person
        contact_email = "" if club.contact_email in {"", "nan"} else club.contact_email
        contact_phone = "" if club.contact_phone in {"", "nan"} else club.contact_phone
        city = "" if club.city in {"", "nan"} else club.city
        cleaned_clubs.append(
            {
                "id": club.id,
                "team_name": club.team_name,
                "region": club.region or "",
                "city": city,
                "contact_person": contact_person,
                "contact_email": contact_email,
                "contact_phone": contact_phone,
                "has_contact": any([contact_person, contact_email, contact_phone]),
            }
        )

    data = {
        "clubs": cleaned_clubs,
        "clubs_count": base_clubs.count(),
        "regions_count": base_clubs.values("region").distinct().count(),
        "contact_clubs_count": base_clubs.filter(
            (Q(contact_person__gt="") & ~Q(contact_person="nan"))
            | (Q(contact_email__gt="") & ~Q(contact_email="nan"))
            | (Q(contact_phone__gt="") & ~Q(contact_phone="nan"))
        ).count(),
        "filtered_count": len(cleaned_clubs),
        "regions": sorted(filter(None, base_clubs.values_list("region", flat=True).order_by("region").distinct())),
        "query": query,
        "selected_region": selected_region,
        "has_active_filters": bool(query or selected_region),
    }

    return render(request, "club/clubs-list.html", data)


def club_detail_view(request, pk):
    riders_of_club_count = Rider.objects.filter(is_active=True, is_approved=True, club=pk).count()
    club = get_object_or_404(Club, pk=pk)
    this_year = date.today().year
    events = Event.objects.filter(organizer=club.id, date__year=str(this_year)).order_by('date')

    data = {'club': club, 'riders_of_club_count': riders_of_club_count, 'events': events}

    return render(request, 'club/club-detail.html', data)


@staff_member_required
def riders_on_events_export_view(request, pk):
    club = get_object_or_404(Club, pk=pk)
    file_path = riders_on_events(pk)

    if not file_path or not os.path.exists(file_path):
        raise Http404("Export účasti jezdců nebyl vygenerován.")

    relative_path = Path(file_path).resolve().relative_to(Path(settings.MEDIA_ROOT).resolve())

    return FileResponse(
        (club.riders_on_events.storage if club.riders_on_events else None or Club._meta.get_field("riders_on_events").storage).open(str(relative_path), "rb"),
        as_attachment=True,
        filename=os.path.basename(file_path),
    )

class Participation:
    name = ""
    sum = 0
    count = 0
    date = ""


def participation_in_races(request, pk):
    """ Function for calculate how many riders was in the events and how many money was paid by club in current year"""
    this_year = date.today().year
    club = get_object_or_404(Club, pk=pk)

    entries_qs = (
        Entry.objects.filter(
            event__date__year=this_year,
            checkout=False,
            rider__club=club,
        )
        .values('event__id', 'event__name', 'event__date')
        .annotate(
            count=Count('id'),
            total_fees=Sum(F('fee_20') + F('fee_24') + F('fee_beginner')),
        )
        .filter(total_fees__gt=0)
        .order_by('event__date')
    )

    part_in_events = []
    total_sum = 0
    for row in entries_qs:
        part = Participation()
        part.name = row['event__name']
        part.date = row['event__date']
        part.count = row['count']
        part.sum = row['total_fees']
        part_in_events.append(part)
        total_sum += row['total_fees']

    data = {'club': club, 'participations': part_in_events, 'sum': total_sum, 'year': this_year}
    return render(request, 'club/club-participation.html', data)


def mapa_klubu(request):
    kluby = Club.objects.filter(is_active=True).exclude(lon=0, lng=0)

    upravene_kluby = []
    for klub in kluby:
        lon = str(klub.lon).replace(',', '.')
        lng = str(klub.lng).replace(',', '.')
        upravene_kluby.append({
            'team_name': klub.team_name,
            'city': klub.city,
            'lon': lon,
            'lng': lng,
            'web': klub.web,
        })

    return render(request, 'club/maps.html', {'kluby': upravene_kluby})
