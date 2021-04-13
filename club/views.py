from django.shortcuts import render, get_object_or_404
from .models import Club
from rider.models import Rider
from event.models import Event
from datetime import date

# Create your views here.

def ClubsListView(request):
    clubs = Club.objects.filter(is_active=True)
    data = {'clubs': clubs}

    return render(request, 'club/clubs-list.html', data)


def ClubDetailView(request, pk):
    riders_of_club_count = Rider.objects.filter(is_active=True, is_approwe=True, club=pk).count()
    club = get_object_or_404(Club, pk=pk)
    this_year = date.today().year
    events = Event.objects.filter(organizer=club.id, date__year=str(this_year))
    data = {'club': club, 'riders_of_club_count': riders_of_club_count, 'events': events}

    return render(request, 'club/club-detail.html', data)
