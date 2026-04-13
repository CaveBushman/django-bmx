import os
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404
from django.shortcuts import render, get_object_or_404
from django.db.models import Sum, Count, F
from .models import Club
from rider.models import Rider
from event.models import Event, Entry
from datetime import date
from .func import riders_on_events
# import folium


# Create your views here.

def clubs_list_view(request):
    clubs = Club.objects.filter(is_active=True).order_by('team_name')
    data = {
        'clubs': clubs,
        'clubs_count': clubs.exclude(team_name="Bez klubové příslušnosti").count(),
        'regions_count': clubs.exclude(team_name="Bez klubové příslušnosti").values('region').distinct().count(),
        'contact_clubs_count': clubs.exclude(team_name="Bez klubové příslušnosti").exclude(contact_email="").count(),
    }

    return render(request, 'club/clubs-list.html', data)


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

    return FileResponse(
        open(file_path, "rb"),
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
