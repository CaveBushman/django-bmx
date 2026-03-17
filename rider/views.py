import logging
import os
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.utils import timezone

logger = logging.getLogger(__name__)
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.views.decorators.cache import cache_control
from django.db.models import Count, Q
from django.contrib.admin.views.decorators import staff_member_required
from bmx import settings
from .models import Rider, ForeignRider
from .rider import (
    two_years_inactive,
    CheckValidLicenceThread,
    Participation,
    Cruiser,
    RiderSetClassesThread,
    first_line_riders_by_club_and_class,
    RiderQualifyToCNThread,
)
from rider.rider import set_all_riders_classes
from club.models import Club
import json
from event.models import Event, RaceRun, Result
from ranking.ranking import RankPositionCount
import datetime
from datetime import date
import requests
import requests.packages
from decouple import config
from openpyxl import Workbook
from rider.rider import get_rider_data
from rider.subscriptions import (
    cancel_rider_stats_subscription,
    get_active_rider_stats_subscription,
    get_current_season_settings,
    has_active_rider_stats_access,
    purchase_rider_stats_subscription,
    resume_rider_stats_subscription,
)
from rider.models import RiderStatsSubscription

# Global variables
now = date.today().year


# Create your views here.

def can_manage_premium_stats(user):
    return user.is_authenticated and (user.is_admin or user.is_superuser or user.is_staff)


admin_required = user_passes_test(can_manage_premium_stats, login_url="/login/")


def riders_list_view(request):
    riders = (
        Rider.objects.filter(is_active=True, is_approved=True)
        .select_related("club")
        .only(
            "uci_id",
            "first_name",
            "last_name",
            "photo",
            "valid_licence",
            "is_qualify_to_cn_20",
            "is_qualify_to_cn_24",
            "club__team_name",
            "club__id",
            "is_20",
            "is_24",
            "class_20",
            "class_24",
            "plate",
            "plate_color_20",
        )
        .order_by("last_name", "first_name")
    )

    last_name_query = (request.GET.get("last_name") or "").strip()
    club_query = (request.GET.get("club") or "").strip()
    plate_query = (request.GET.get("plate") or "").strip()

    if last_name_query:
        riders = riders.filter(last_name__icontains=last_name_query)
    if club_query:
        riders = riders.filter(club__team_name__icontains=club_query)
    if plate_query:
        try:
            riders = riders.filter(plate=int(plate_query))
        except ValueError:
            riders = riders.none()

    paginator = Paginator(riders, 100)
    page_obj = paginator.get_page(request.GET.get("page"))

    metrics_queryset = Rider.objects.filter(is_active=True, is_approved=True)
    data = {
        "riders": page_obj.object_list,
        "page_obj": page_obj,
        "total_riders": metrics_queryset.count(),
        "valid_licence_riders": metrics_queryset.filter(valid_licence=True).count(),
        "clubs_count": metrics_queryset.exclude(club__isnull=True).values("club").distinct().count(),
        "last_name_query": last_name_query,
        "club_query": club_query,
        "plate_query": plate_query,
    }

    return render(request, "rider/riders-list.html", data)


def rider_detail_view(request, pk):
    rider = get_object_or_404(Rider, uci_id=pk)
    results = Result.objects.filter(
        rider_id=rider.uci_id,
        date__gte=datetime.datetime.now() - datetime.timedelta(days=365),
    ).order_by("date")
    season_settings = get_current_season_settings()
    premium_access = has_active_rider_stats_access(request.user, rider)
    active_subscription = get_active_rider_stats_subscription(request.user, rider)
    premium_runs_count = RaceRun.objects.filter(rider=rider).count()
    data = {
        "rider": rider,
        "results": results,
        "premium_access": premium_access,
        "active_subscription": active_subscription,
        "premium_runs_count": premium_runs_count,
        "premium_price": season_settings.rider_stats_monthly_price if season_settings else None,
        "can_manage_premium_stats": can_manage_premium_stats(request.user),
    }
    return render(request, "rider/rider-detail.html", data)


@admin_required
def rider_premium_stats_subscribe_view(request, pk):
    rider = get_object_or_404(Rider, uci_id=pk)
    if request.method != "POST":
        return redirect("rider:detail", pk=pk)

    try:
        subscription, created = purchase_rider_stats_subscription(request.user, rider)
    except ValueError as error:
        messages.error(request, str(error))
        return redirect("rider:detail", pk=pk)

    if created:
        messages.success(
            request,
            f"Prémiové statistiky jezdce {rider.first_name} {rider.last_name} jsou aktivní do {timezone.localtime(subscription.expires_at):%d.%m.%Y %H:%M}.",
        )
    else:
        messages.info(request, "Prémiové statistiky tohoto jezdce už máš aktivní.")

    return redirect("rider:premium-stats", pk=pk)


@admin_required
def rider_premium_stats_view(request, pk):
    rider = get_object_or_404(Rider, uci_id=pk)
    if not has_active_rider_stats_access(request.user, rider):
        messages.error(request, "Pro rozšířené časy z tratí potřebuješ aktivní předplatné tohoto jezdce.")
        return redirect("rider:detail", pk=pk)

    runs = (
        RaceRun.objects.filter(rider=rider)
        .select_related("event", "result")
        .order_by("-event__date", "round_type", "round_number", "id")
    )
    subscription = get_active_rider_stats_subscription(request.user, rider)
    data = {
        "rider": rider,
        "runs": runs,
        "subscription": subscription,
    }
    return render(request, "rider/rider-premium-stats.html", data)


@admin_required
def rider_premium_subscriptions_view(request):
    if request.method == "POST":
        subscription = get_object_or_404(
            RiderStatsSubscription.objects.select_related("rider"),
            pk=request.POST.get("subscription_id"),
            user=request.user,
        )
        action = request.POST.get("action")
        if action == "disable-renew":
            cancel_rider_stats_subscription(subscription)
            messages.success(
                request,
                f"Automatické obnovování pro {subscription.rider.first_name} {subscription.rider.last_name} bylo vypnuto.",
            )
        elif action == "enable-renew":
            resume_rider_stats_subscription(subscription)
            messages.success(
                request,
                f"Automatické obnovování pro {subscription.rider.first_name} {subscription.rider.last_name} bylo zapnuto.",
            )
        elif action == "delete":
            rider_name = f"{subscription.rider.first_name} {subscription.rider.last_name}"
            subscription.delete()
            messages.success(
                request,
                f"Předplatné jezdce {rider_name} bylo smazáno z přehledu.",
            )
        return redirect("rider:premium-subscriptions")

    current_time = timezone.now()
    subscriptions = list(
        RiderStatsSubscription.objects.filter(user=request.user)
        .select_related("rider", "season")
        .order_by("-expires_at", "rider__last_name", "rider__first_name")
    )
    for subscription in subscriptions:
        subscription.can_delete = (
            not subscription.auto_renew and subscription.expires_at <= current_time
        )
    return render(
        request,
        "rider/rider-premium-subscriptions.html",
        {"subscriptions": subscriptions},
    )


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@staff_member_required
def rider_admin(request):
    total_riders = Rider.objects.filter().count()
    active_riders = Rider.objects.filter(is_active=True).count()
    data = {"total_riders": total_riders, "active_riders": active_riders}
    return render(request, "rider/rider-admin.html", data)


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@staff_member_required
def free_plates_view(request):
    used_plates = set(
        Rider.objects.filter(is_active=True)
        .exclude(plate__isnull=True)
        .values_list("plate", flat=True)
    )
    free_plates = [plate for plate in range(10, 1000) if plate not in used_plates]

    data = {
        "free_plates": free_plates,
        "free_plates_count": len(free_plates),
    }
    return render(request, "rider/rider-free-plates.html", data)


def _rider_request_context(**extra):
    clubs = Club.objects.filter(is_active=True)
    used_plates = list(
        Rider.objects.filter(is_active=True).values_list("plate", flat=True)
    )
    free_plates = [plate for plate in range(10, 1000) if plate not in used_plates]

    context = {
        "clubs": clubs,
        "free_plates": free_plates,
        "lookup_url": "/rider/new/licence-lookup",
    }
    context.update(extra)
    return context


def rider_licence_lookup_view(request):
    uci_id = (request.GET.get("uci_id") or "").strip()
    if not uci_id.isdigit() or len(uci_id) != 11:
        return JsonResponse(
            {"ok": False, "message": "UCI ID musí obsahovat přesně 11 číslic."},
            status=400,
        )

    if Rider.objects.filter(uci_id=uci_id).exists():
        existing = Rider.objects.get(uci_id=uci_id)
        return JsonResponse(
            {
                "ok": False,
                "message": f"Jezdec {existing.first_name} {existing.last_name} už má přidělené startovní číslo.",
            },
            status=409,
        )

    data_json, error_msg = get_rider_data(uci_id)
    if error_msg or not data_json:
        return JsonResponse(
            {"ok": False, "message": "Licence nebyla nalezena."},
            status=404,
        )

    first_name = data_json.get("firstName", "").strip()
    last_name = data_json.get("lastName", "").strip()
    birth = (data_json.get("birth", "") or "")[:10]
    gender_code = data_json.get("sex", {}).get("code", "M")
    gender = "Žena" if gender_code == "F" else "Muž"

    return JsonResponse(
        {
            "ok": True,
            "rider": {
                "uci_id": uci_id,
                "first_name": first_name,
                "last_name": last_name.capitalize() if last_name else "",
                "date_of_birth": birth,
                "gender": gender,
            },
        }
    )


def rider_new_view(request):
    if request.method == "POST":
        context = _rider_request_context(
            first_name=request.POST.get("first_name", ""),
            last_name=request.POST.get("last_name", ""),
            date_of_birth=request.POST.get("date_of_birth", ""),
            gender=request.POST.get("gender", ""),
            uci_id=request.POST.get("uci_id", ""),
            lookup_confirmed=request.POST.get("lookup_confirmed", ""),
            selected_plate=request.POST.get("plate", ""),
            selected_club=request.POST.get("club", ""),
            is20_checked="is20" in request.POST,
            is24_checked="is24" in request.POST,
            elite_checked="elite" in request.POST,
            emergency_contact=request.POST.get("emergency-contact", ""),
            emergency_phone=request.POST.get("emergency-phone", ""),
        )

        required_fields = {
            "uci_id": "UCI ID",
            "first_name": "Jméno",
            "last_name": "Příjmení",
            "date_of_birth": "Datum narození",
            "plate": "Startovní číslo",
            "club": "Klub",
            "emergency-contact": "Nouzový kontakt",
            "emergency-phone": "Telefon nouzového kontaktu",
        }
        for field, label in required_fields.items():
            if not request.POST.get(field) or request.POST.get(field) in {"", "Vyber..."}:
                messages.error(request, f"Pole {label} je povinné.")
                return render(request, "rider/rider-request.html", context)

        if request.POST.get("lookup_confirmed") != "1":
            messages.error(request, "Nejprve ověř UCI ID proti licenci ČSC.")
            return render(request, "rider/rider-request.html", context)

        uci_id = request.POST["uci_id"].strip()
        if not uci_id.isdigit() or len(uci_id) != 11:
            messages.error(request, "UCI ID musí obsahovat přesně 11 číslic.")
            return render(request, "rider/rider-request.html", context)

        if Rider.objects.filter(uci_id=uci_id).exists():
            existing = Rider.objects.get(uci_id=uci_id)
            messages.error(
                request,
                f"Jezdec/jezdkyně {existing.first_name} {existing.last_name}, UCI ID {uci_id}, již má přidělené číslo.",
            )
            return render(request, "rider/rider-request.html", context)

        data_json, error_msg = get_rider_data(uci_id)
        if error_msg or not data_json:
            messages.error(request, error_msg or "Licence UCI ID nebyla nalezena.")
            return render(request, "rider/rider-request.html", context)

        if "is20" not in request.POST and "is24" not in request.POST:
            messages.error(request, 'Musíš vybrat, zda budeš jezdit 20" nebo 24" kolo.')
            return render(request, "rider/rider-request.html", context)

        Rider.objects.create(
            first_name=request.POST["first_name"].strip(),
            last_name=request.POST["last_name"].strip(),
            date_of_birth=datetime.datetime.strptime(
                request.POST["date_of_birth"], "%Y-%m-%d"
            ),
            gender=request.POST.get("gender", "Muž"),
            uci_id=uci_id,
            is_20="is20" in request.POST,
            is_24="is24" in request.POST,
            is_elite="elite" in request.POST,
            plate=request.POST["plate"],
            club=Club.objects.get(id=request.POST["club"]),
            is_active=True,
            is_approved=False,
            emergency_contact=request.POST["emergency-contact"],
            emergency_phone=request.POST["emergency-phone"],
        )
        return render(request, "rider/rider-request-success.html")

    return render(request, "rider/rider-request.html", _rider_request_context())


@staff_member_required
def inactive_riders_views(request):
    """ Function for views inactive riders, only request params"""
    inactive_riders = two_years_inactive()
    data = {"riders": inactive_riders, "sum": len(inactive_riders)}
    return render(request, "rider/rider-inactive.html", data)


@staff_member_required
def licence_check_views(request):
    """ Function for checking valid licence"""
    CheckValidLicenceThread().start()
    messages.success(request, "Ověřování platnosti licencí probíhá na pozadí.")
    data = {}
    return render(request, "rider/rider-success.html", data)


@staff_member_required
def ranking_count_views(request):
    """ Function for recount ranking"""
    RankPositionCount().count_ranking_position()
    return render(request, "rider/rider-rank.html")


@staff_member_required
def participation_riders_on_event(request):
    participation = Participation().count()

    file_path = os.path.join(settings.MEDIA_ROOT, "participation/participation.xlsx")
    if os.path.exists(file_path):
        with open(file_path, "rb") as fh:
            response = HttpResponse(fh.read(), content_type="application/vnd.ms-excel")
            response["Content-Disposition"] = "inline; filename=" + os.path.basename(
                file_path
            )
            return response


@staff_member_required
def recalculate_riders_classes(request):
    # set_all_riders_classes()
    RiderSetClassesThread().start()
    messages.success(request, "Kategorie jezdců jsou přepočítávány na pozadí.")
    data = {}
    return render(request, "rider/rider-success.html", data)


@staff_member_required
def calculate_cruiser_median(request):
    year_options = list(_get_event_year_options())
    selected_year = _resolve_selected_year(request.GET.get("year"), year_options)

    cruiser = Cruiser()
    cruiser.year = int(selected_year)
    cruiser_data = cruiser.calculate_median()
    cruiser_results = cruiser_data["cruisers"]
    count_cruiser_results = len(cruiser_results)

    data = {
        "cruisers": cruiser_results,
        "sum": count_cruiser_results,
        "selected_year": int(selected_year),
        "year_options": year_options,
        "median_age": cruiser_data["median_age"],
        "cup_events": cruiser_data["cup_events"],
        "minimum_participations": cruiser_data["minimum_participations"],
    }
    return render(request, "rider/rider-cruiser.html", data)


@staff_member_required
def riders_by_class_and_club(request):

    clubs = Club.objects.filter(is_active=True).order_by("team_name")
    file_name = "RIDERS_BY_CLUB_AND_CLASS.xlsx"

    response = HttpResponse(content_type="application/ms-excel")
    response["Content-Disposition"] = f'attachment; filename="{file_name}"'

    # Jeden DB dotaz místo 33 × počet klubů
    counts_qs = (
        Rider.objects.filter(is_active=True, is_approved=True)
        .values("club_id", "class_20")
        .annotate(count=Count("id"))
    )
    counts = {(row["club_id"], row["class_20"]): row["count"] for row in counts_qs}

    CLASSES = [
        "Boys 6", "Boys 7", "Girls 7", "Boys 8", "Girls 8",
        "Boys 9", "Girls 9", "Boys 10", "Girls 10", "Boys 11", "Girls 11",
        "Boys 12", "Girls 12", "Boys 13", "Girls 13", "Boys 14", "Girls 14",
        "Boys 15", "Girls 15", "Boys 16", "Girls 16",
        "Men 17-24", "Women 17-24", "Men 25-29", "Women 25 and over",
        "Men 30-34", "Men 35 and over", "Men Junior", "Women Junior",
        "Men Under 23", "Women Under 23", "Men Elite", "Women Elite",
    ]

    wb = Workbook()
    ws = wb.active

    first_line_riders_by_club_and_class(ws)

    row = 2
    for club in clubs:
        ws.cell(row, 1, club.team_name)
        for col, cls in enumerate(CLASSES, start=2):
            ws.cell(row, col, counts.get((club.id, cls), 0))
        row += 1
    wb.save(response)

    return response


@staff_member_required
def qualify_to_cn(request):
    RiderQualifyToCNThread().start()
    messages.success(
        request, "Kvalifikace na Mistrovství České republiky je počítána na pozadí."
    )
    data = {}
    return render(request, "rider/rider-success.html", data)
def _get_event_year_options():
    return Event.objects.exclude(date__isnull=True).dates("date", "year", order="DESC")


def _resolve_selected_year(selected_year, year_options):
    if selected_year is None:
        return str(year_options[0].year) if year_options else str(date.today().year)
    if not selected_year.isdigit():
        return str(year_options[0].year) if year_options else str(date.today().year)
    return selected_year


def transponder_search_view(request):
    transponder_query = (request.GET.get("transponder") or "").strip().upper()
    results = []

    if transponder_query:
        czech_riders = Rider.objects.filter(
            Q(transponder_20__icontains=transponder_query)
            | Q(transponder_24__icontains=transponder_query)
        ).select_related("club")

        foreign_riders = ForeignRider.objects.filter(
            Q(transponder_20__icontains=transponder_query)
            | Q(transponder_24__icontains=transponder_query)
        )

        for rider in czech_riders:
            matched_in = []
            if (rider.transponder_20 or "").upper() == transponder_query:
                matched_in.append('20"')
            if (rider.transponder_24 or "").upper() == transponder_query:
                matched_in.append('24"')

            results.append(
                {
                    "first_name": rider.first_name,
                    "last_name": rider.last_name,
                    "club": rider.club.team_name if rider.club else "-",
                    "plate": rider.plate or "-",
                }
            )

        for rider in foreign_riders:
            matched_in = []
            if (rider.transponder_20 or "").upper() == transponder_query:
                matched_in.append('20"')
            if (rider.transponder_24 or "").upper() == transponder_query:
                matched_in.append('24"')

            results.append(
                {
                    "first_name": rider.first_name,
                    "last_name": rider.last_name,
                    "club": rider.club or rider.state or "-",
                    "plate": rider.plate or "-",
                }
            )

    data = {
        "transponder_query": transponder_query,
        "results": results,
        "has_search": bool(transponder_query),
    }
    return render(request, "rider/transponder-search.html", data)


def plate_search_view(request):
    plate_query = (request.GET.get("plate") or "").strip()
    results = []

    if plate_query and plate_query.isdigit():
        czech_riders = Rider.objects.filter(
            plate=int(plate_query), is_active=True
        ).select_related("club")
        foreign_riders = ForeignRider.objects.filter(plate=int(plate_query))

        for rider in czech_riders:
            results.append(
                {
                    "plate": rider.plate or "-",
                    "first_name": rider.first_name,
                    "last_name": rider.last_name,
                    "club": rider.club.team_name if rider.club else "-",
                }
            )

        for rider in foreign_riders:
            results.append(
                {
                    "plate": rider.plate or "-",
                    "first_name": rider.first_name,
                    "last_name": rider.last_name,
                    "club": rider.club or rider.state or "-",
                }
            )

    data = {
        "plate_query": plate_query,
        "results": results,
        "has_search": bool(plate_query),
    }
    return render(request, "rider/plate-search.html", data)
