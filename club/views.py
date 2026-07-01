import os
from pathlib import Path
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum, Count, F, Q
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.translation import gettext as _

from .forms import McrClubTeamForm
from .models import Club, McrClubTeam
from event.models import SeasonSettings
from rider.models import Rider
from event.models import Event, Entry
from .func import riders_on_events
# import folium


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


def can_access_mcr_club_teams(user):
    return user.is_authenticated and (
        getattr(user, "is_club_manager", False)
        or getattr(user, "is_admin", False)
        or getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
    )


mcr_club_teams_required = user_passes_test(can_access_mcr_club_teams, login_url="/login/")


def _get_managed_club(user):
    if getattr(user, "club_id", None):
        return user.club
    return None


def is_mcr_club_registration_open(year):
    season = SeasonSettings.objects.filter(year=year).first()
    if season is None:
        return True
    return bool(season.mcr_club_registration_open)


def _render_mcr_registration_closed(request, year, club=None):
    return render(
        request,
        "club/mcr-registration-closed.html",
        {"year": year, "club": club},
        status=403,
    )


@login_required
@mcr_club_teams_required
def mcr_club_teams_redirect_view(request):
    current_year = date.today().year
    if not is_mcr_club_registration_open(current_year):
        return _render_mcr_registration_closed(request, current_year, _get_managed_club(request.user))
    return redirect("club:mcr-club-teams", year=current_year)


@login_required
@mcr_club_teams_required
def mcr_club_teams_view(request, year):
    club = _get_managed_club(request.user)
    if club is None:
        return HttpResponseForbidden(_("K účtu není přiřazený klub pro správu družstev."))
    if not is_mcr_club_registration_open(year):
        return _render_mcr_registration_closed(request, year, club)

    teams = (
        McrClubTeam.objects.filter(year=year, club=club)
        .prefetch_related("members__rider")
        .order_by("name")
    )
    selected_team = None
    selected_team_id = request.GET.get("team")
    if selected_team_id:
        selected_team = get_object_or_404(McrClubTeam, pk=selected_team_id, year=year, club=club)
    show_form = bool(selected_team_id or request.GET.get("new"))

    if request.method == "POST":
        show_form = True
        action = request.POST.get("action", "save")
        posted_team_id = request.POST.get("team_id")
        posted_team = None
        if posted_team_id:
            posted_team = get_object_or_404(McrClubTeam, pk=posted_team_id, year=year, club=club)

        if action == "delete" and posted_team:
            posted_team.delete()
            messages.success(request, _("Družstvo bylo odstraněno."))
            return redirect("club:mcr-club-teams", year=year)

        form = McrClubTeamForm(request.POST, club=club, year=year, team=posted_team, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("Družstvo bylo uloženo."))
            return redirect("club:mcr-club-teams", year=year)
        selected_team = posted_team
    else:
        form = McrClubTeamForm(club=club, year=year, team=selected_team, user=request.user) if show_form else None

    return render(
        request,
        "club/mcr-club-teams.html",
        {
            "club": club,
            "year": year,
            "previous_year": year - 1,
            "next_year": year + 1,
            "teams": teams,
            "selected_team": selected_team,
            "show_form": show_form,
            "form": form,
        },
    )


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
        # Explicitně — mimetypes.guess_type na minimálním Linuxu (slim/CI) nezná
        # .xlsx a vrátil by application/octet-stream.
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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
