import logging
import os
import re
from collections import defaultdict
from statistics import mean, median, pstdev
from openpyxl import Workbook
from PIL import Image, UnidentifiedImageError
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.utils import timezone

logger = logging.getLogger(__name__)
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.translation import gettext as _, gettext_lazy as _gl, ngettext
from django.core.cache import cache
from django.contrib import messages
from django.core.paginator import Paginator
from django.views.decorators.cache import cache_control
from django.db.models import Count, Q
from django.contrib.admin.views.decorators import staff_member_required
from bmx import settings
from bmx.form_protection import build_security_context, protect_public_flow
from bmx.text_normalization import normalize_search_text
from accounts.models import AvatarChangeRequest
from rider.models import Rider, ForeignRider, RiderTransponderChange
from rider.rider import (
    two_years_inactive,
    start_licence_check,
    Participation,
    Cruiser,
    RiderSetClassesThread,
    first_line_riders_by_club_and_class,
    RiderQualifyToCNThread,
)
from club.models import Club
from event.models import Event, RaceRun, Result
from ranking.ranking import RANKING_RECOUNT_RUNNING_KEY, schedule_ranking_recount
import datetime
from datetime import date
from rider.rider import get_rider_data
from rider.subscriptions import (
    cancel_rider_stats_subscription,
    get_active_rider_stats_subscription,
    get_active_trainer_club_subscription,
    get_current_season_settings,
    has_active_trainer_club_extended_access,
    has_active_trainer_club_stats_access,
    purchase_rider_stats_subscription,
    resume_rider_stats_subscription,
)
from rider.models import MobileAppSubscription, RiderStatsSubscription, TrainerClubSubscription
from rider.mobile_subscriptions import (
    cancel_mobile_app_subscription,
    get_active_mobile_app_subscription,
    get_current_season_settings,
    purchase_mobile_app_subscription,
    resume_mobile_app_subscription,
)
from finance.models import EventInvoice, SubscriptionInvoice
from finance.subscription_invoices import SubscriptionInvoiceService
from rider.plates import display_plate, generate_available_plate_values, legacy_plate_int, normalize_plate_value
from rider.trainer_dashboard import (
    build_club_kpi_export_rows,
    build_club_riders_export_rows,
    build_trainer_dashboard_context,
    build_trainer_export_filename,
    export_rows_as_csv,
    export_rows_as_xlsx,
    get_exportable_trainer_club_or_403,
    normalize_export_format_or_404,
    handle_trainer_dashboard_post,
)
from rider.premium_stats_pdf import (
    build_rider_premium_stats_pdf,
    build_rider_premium_stats_pdf_filename,
)


from rider.views._common import *  # noqa: F401,F403
from rider.views._common import (  # podtržítkové helpery (import * je nepřenáší)
    _get_manageable_inactive_riders,
    _get_trainer_club_stats_subscription_for_rider,
    _get_premium_access_context,
    _validate_avatar_upload,
    _get_pending_avatar_request_for_target,
    _can_export_rider_premium_stats_pdf,
    _resolve_kpi_period,
    _build_rider_premium_stats_context,
    _parse_numeric_place,
    _safe_mean,
    _safe_median,
    _safe_stddev,
    _safe_rate,
    _clamp_score,
    _percentile_better_than,
    _get_table_column_key,
    _overall_result_places,
    _matches_wheel_filter,
    _build_chart_series,
    _build_track_options,
    _resolve_selected_track,
    _build_peer_context,
    _build_head_to_head,
    _build_track_stats,
    _rider_request_context,
    _render_rider_request,
    _get_event_year_options,
    _resolve_selected_year,
)


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@staff_member_required
def rider_admin(request):
    AvatarChangeRequest.expire_stale_requests()
    total_riders = Rider.objects.filter().count()
    active_riders = Rider.objects.filter(is_active=True).count()
    qualified_to_mcr_count = Rider.objects.filter(
        is_active=True,
        is_approved=True,
    ).filter(
        Q(is_qualify_to_cn_20=True) | Q(is_qualify_to_cn_24=True)
    ).count()
    pending_avatar_count = AvatarChangeRequest.objects.filter(
        status=AvatarChangeRequest.STATUS_PENDING
    ).count()
    data = {
        "total_riders": total_riders,
        "active_riders": active_riders,
        "qualified_to_mcr_count": qualified_to_mcr_count,
        "pending_avatar_count": pending_avatar_count,
    }
    return render(request, "rider/rider-admin.html", data)



@login_required(login_url="/login/")
@inactive_riders_required
def inactive_riders_views(request):
    """ Function for views inactive riders, only request params"""
    inactive_riders = _get_manageable_inactive_riders(request.user)
    data = {
        "riders": inactive_riders,
        "sum": len(inactive_riders),
        "managed_club": request.user.club if getattr(request.user, "is_club_manager", False) and request.user.club_id else None,
    }
    return render(request, "rider/rider-inactive.html", data)



@login_required(login_url="/login/")
@inactive_riders_required
def deactivate_inactive_rider_view(request, rider_id):
    if request.method != "POST":
        return redirect("rider:inactive")

    inactive_rider_ids = {rider.pk for rider in _get_manageable_inactive_riders(request.user)}
    rider = get_object_or_404(Rider, pk=rider_id)

    if rider.pk not in inactive_rider_ids:
        messages.error(request, _("Jezdce nelze deaktivovat mimo seznam neaktivních jezdců."))
        return redirect("rider:inactive")

    rider.is_active = False
    rider.save(update_fields=["is_active"])
    logger.info(
        "Rider deactivated from inactive list by user_id=%s email=%s role_admin=%s role_club_manager=%s rider_id=%s rider_uci_id=%s club_id=%s",
        request.user.pk,
        request.user.email,
        getattr(request.user, "is_admin", False),
        getattr(request.user, "is_club_manager", False),
        rider.pk,
        rider.uci_id,
        rider.club_id,
    )
    messages.success(
        request,
        _("Jezdec %(name)s byl označen jako neaktivní.") % {'name': f"{rider.first_name} {rider.last_name}"}
    )
    return redirect("rider:inactive")



@staff_member_required
def licence_check_views(request):
    """ Function for checking valid licence"""
    started = start_licence_check()
    if started:
        data = {
            "status_eyebrow": _("Správa jezdců"),
            "status_title": _("Kontrola licencí byla spuštěna"),
            "status_description": _("Ověřování platnosti licencí nyní běží na pozadí. Po dokončení se stav propíše přímo v databázi jezdců."),
            "status_note": _("Není potřeba čekat na této stránce. Můžeš pokračovat v administraci nebo se vrátit zpět na přehled nástrojů."),
            "status_icon": "license",
            "primary_action_label": _("Zpět na administraci jezdců"),
            "primary_action_url": "rider:admin",
            "secondary_action_label": _("Seznam jezdců"),
            "secondary_action_url": "rider:list",
        }
    else:
        data = {
            "status_eyebrow": _("Správa jezdců"),
            "status_title": _("Kontrola licencí již probíhá"),
            "status_description": _("Ověřování platnosti licencí již běží na pozadí. Počkej na dokončení předchozího průchodu."),
            "status_note": _("Není potřeba spouštět kontrolu znovu. Výsledky se propíší do databáze automaticky."),
            "status_icon": "license",
            "primary_action_label": _("Zpět na administraci jezdců"),
            "primary_action_url": "rider:admin",
            "secondary_action_label": _("Seznam jezdců"),
            "secondary_action_url": "rider:list",
        }
    return render(request, "rider/rider-success.html", data)



@staff_member_required
def ranking_count_views(request):
    """ Function for recount ranking"""
    try:
        recount_already_running = bool(cache.get(RANKING_RECOUNT_RUNNING_KEY))
        schedule_ranking_recount()
        if recount_already_running:
            messages.info(request, _("Přepočet rankingu už běží. Další průchod byl zařazen do fronty."))
        else:
            messages.info(request, _("Přepočet rankingu byl spuštěn na pozadí."))
    except Exception as error:
        logger.exception("Naplánování přepočtu rankingu selhalo")
        messages.error(
            request,
            _("Při naplánování přepočtu rankingu došlo k následující chybě: %(message)s")
            % {"message": error},
        )
    return redirect("rider:admin")



@staff_member_required
def recalculate_riders_classes(request):
    # set_all_riders_classes()
    RiderSetClassesThread().start()
    data = {
        "status_eyebrow": _("Správa jezdců"),
        "status_title": _("Přepočet kategorií byl spuštěn"),
        "status_description": _("Kategorie jezdců se teď přepočítávají na pozadí podle aktuálních pravidel."),
        "status_note": _("Po dokončení se nové třídy propíšou do profilů jezdců. Můžeš se vrátit do administrace nebo pokračovat v jiné práci."),
        "status_icon": "classes",
        "primary_action_label": _("Zpět na administraci jezdců"),
        "primary_action_url": "rider:admin",
        "secondary_action_label": _("Seznam jezdců"),
        "secondary_action_url": "rider:list",
    }
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
def qualify_to_cn(request):
    RiderQualifyToCNThread().start()
    data = {
        "status_eyebrow": _("Správa jezdců"),
        "status_title": _("Výpočet kvalifikace byl spuštěn"),
        "status_description": _("Kvalifikace na Mistrovství České republiky se právě počítá na pozadí."),
        "status_note": _("Po dokončení budou nové výsledky dostupné v příslušném přehledu. Není potřeba čekat na této stránce."),
        "status_icon": "qualify",
        "primary_action_label": _("Zpět na administraci jezdců"),
        "primary_action_url": "rider:admin",
        "secondary_action_label": _("Seznam jezdců"),
        "secondary_action_url": "rider:list",
    }
    return render(request, "rider/rider-success.html", data)


__all__ = [
    'rider_admin',
    'inactive_riders_views',
    'deactivate_inactive_rider_view',
    'licence_check_views',
    'ranking_count_views',
    'recalculate_riders_classes',
    'calculate_cruiser_median',
    'qualify_to_cn',
]
