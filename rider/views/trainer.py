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


@trainer_dashboard_required
def trainer_dashboard_view(request):
    if request.method == "POST":
        post_response = handle_trainer_dashboard_post(request)
        if post_response is not None:
            return post_response

    context = build_trainer_dashboard_context(request.user)
    return render(request, "rider/trainer-dashboard.html", context)



@trainer_dashboard_required
def trainer_club_riders_export_view(request, club_id, export_format):
    export_format = normalize_export_format_or_404(export_format)
    club = get_exportable_trainer_club_or_403(request.user, club_id)
    rows = build_club_riders_export_rows(club)
    headers = [
        ("uci_id", "UCI ID"),
        ("first_name", "Jméno"),
        ("last_name", "Příjmení"),
        ("class_20", "Kategorie 20\""),
        ("class_24", "Kategorie 24\""),
        ("plate", "Číslo"),
        ("transponder_20", "Transpondér 20\""),
        ("transponder_24", "Transpondér 24\""),
        ("valid_licence", "Platná licence"),
        ("email", "E-mail"),
        ("phone", "Telefon"),
    ]
    filename = build_trainer_export_filename(club, "riders")
    if export_format == "xlsx":
        return export_rows_as_xlsx(f"{filename}.xlsx", "Riders", headers, rows)
    return export_rows_as_csv(f"{filename}.csv", headers, rows)



@trainer_dashboard_required
def trainer_club_kpi_export_view(request, club_id, export_format):
    export_format = normalize_export_format_or_404(export_format)
    club = get_exportable_trainer_club_or_403(request.user, club_id)
    rows = build_club_kpi_export_rows(club)
    headers = [
        ("uci_id", "UCI ID"),
        ("first_name", "Jméno"),
        ("last_name", "Příjmení"),
        ("class_20", "Kategorie 20\""),
        ("class_24", "Kategorie 24\""),
        ("starts_total", "Starty celkem"),
        ("starts_last_2y", "Starty za 2 roky"),
        ("best_result", "Best result"),
        ("avg_place", "Průměrné pořadí"),
        ("median_finish", "Medián finish"),
        ("best_finish", "Best finish"),
        ("median_hill", "Medián hill"),
        ("median_split_1", "Medián split 1"),
    ]
    filename = build_trainer_export_filename(club, "kpi")
    if export_format == "xlsx":
        return export_rows_as_xlsx(f"{filename}.xlsx", "KPI", headers, rows)
    return export_rows_as_csv(f"{filename}.csv", headers, rows)


__all__ = [
    'trainer_dashboard_view',
    'trainer_club_riders_export_view',
    'trainer_club_kpi_export_view',
]
