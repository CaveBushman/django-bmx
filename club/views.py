from django.shortcuts import render, get_object_or_404
from .models import Club
from rider.models import Rider
from event.models import Event, Entry
from datetime import date
# import folium


# Create your views here.

def clubs_list_view(request):
    clubs = Club.objects.filter(is_active=True).order_by('team_name')
    data = {'clubs': clubs}

    return render(request, 'club/clubs-list.html', data)


def club_detail_view(request, pk):
    riders_of_club_count = Rider.objects.filter(is_active=True, is_approwe=True, club=pk).count()
    club = get_object_or_404(Club, pk=pk)
    this_year = date.today().year
    events = Event.objects.filter(organizer=club.id, date__year=str(this_year)).order_by('date')
    data = {'club': club, 'riders_of_club_count': riders_of_club_count, 'events': events}

    return render(request, 'club/club-detail.html', data)

class Participation:
    name = ""
    sum = 0
    count = 0
    date = ""


def participation_in_races(request, pk):
    """ Function for calculate how many riders was in the events and how many money was paid by club in current year"""
    this_year = date.today().year
    club = get_object_or_404(Club, pk=pk)
    events = Event.objects.filter(date__year = str(this_year)).order_by('date')

    part_in_events =[]     
    sum = 0
    for event in events:
        fees = 0
        count = 0

        participation_in_race = Entry.objects.filter(event = event.id, checkout = False)
        riders_in_club = Rider.objects.filter(club = club)

        for rider_in_club in riders_in_club:
            for participation in participation_in_race:
                if participation.rider.id == rider_in_club.id:
                    # print (f"Jezdec {rider_in_club.first_name} {rider_in_club.last_name} se zúčastnil závodu {event.name} se startovným {participation.fee_20}")
                    fees += participation.fee_20 + participation.fee_24 
                    count +=1
                    
        part = Participation()
        part.name = event.name
        part.date = event.date
        part.count = count
        part.sum = fees
        if fees != 0:
            part_in_events.append(part)
        sum += fees
    data = {'club':club, 'participations':part_in_events, 'sum':sum, 'year': this_year}

    return render(request, 'club/club-participation.html', data)


def maps_of_tracks(request):
    """ function for view tracks on map """
    tracks = Club.objects.filter(is_active = True, have_track = True)

    # myMap = folium.Map(location=[49.7439047, 15.3381061], zoom_start=8)
    for track in tracks:
        # folium.Marker([track.lon,track.lng]).add_to(myMap)
        print(f"Přidávám trat na souřadnici {track.lon}, {track.lng}.")
    file_path = 'club/templates/club/mylocation.html'
    # myMap.save(file_path)
    
    return render (request, 'club/mylocation.html')
