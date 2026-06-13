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


@login_required
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
            _("Prémiové statistiky jezdce %(name)s jsou aktivní do %(date)s.") % {'name': f"{rider.first_name} {rider.last_name}", 'date': timezone.localtime(subscription.expires_at).strftime("%d.%m.%Y %H:%M")}
        )
    else:
        messages.info(request, _("Prémiové statistiky tohoto jezdce už máš aktivní."))

    return redirect("rider:premium-stats", pk=pk)



@login_required
def rider_premium_stats_view(request, pk):
    rider = get_object_or_404(Rider, uci_id=pk)
    premium_access_context = _get_premium_access_context(request.user, rider)
    if not premium_access_context["premium_access"]:
        messages.error(
            request,
            _("Pro rozšířené časy z tratí potřebuješ aktivní předplatné tohoto jezdce nebo trenérský přístup přes klub."),
        )
        return redirect("rider:detail", pk=pk)
    return render(
        request,
        "rider/rider-premium-stats.html",
        _build_rider_premium_stats_context(request, rider, premium_access_context),
    )



@login_required
def rider_premium_stats_pdf_view(request, pk):
    rider = get_object_or_404(Rider, uci_id=pk)
    premium_access_context = _get_premium_access_context(request.user, rider)
    if not premium_access_context["premium_access"]:
        messages.error(
            request,
            _("Pro rozšířené časy z tratí potřebuješ aktivní předplatné tohoto jezdce nebo trenérský přístup přes klub."),
        )
        return redirect("rider:detail", pk=pk)
    if not _can_export_rider_premium_stats_pdf(request.user, rider):
        messages.error(
            request,
            _("PDF export premium statistik je dostupný jen pro aktivní trainer extended."),
        )
        return redirect("rider:premium-stats", pk=pk)

    context = _build_rider_premium_stats_context(request, rider, premium_access_context)
    if context["selected_track"] is None:
        messages.error(request, _("Nejdřív vyber trať nebo klub, který chceš exportovat do PDF."))
        return redirect("rider:premium-stats", pk=pk)
    if context["require_wheel_selection"]:
        messages.error(request, _("Pro PDF export nejdřív vyber disciplínu 20\" nebo 24\"."))
        return redirect("rider:premium-stats", pk=pk)
    if context["track_stats"] is None:
        messages.error(request, _("Pro vybranou trať zatím nejsou k dispozici detailní data pro PDF export."))
        return redirect("rider:premium-stats", pk=pk)

    pdf_bytes = build_rider_premium_stats_pdf(
        rider=rider,
        track=context["selected_track"],
        track_stats=context["track_stats"],
        kpi_period=context["kpi_period"],
    )
    filename = build_rider_premium_stats_pdf_filename(rider, context["selected_track"])
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response



@login_required
def rider_compare_view(request, pk):
    rider = get_object_or_404(Rider, uci_id=pk)
    premium_access_context = _get_premium_access_context(request.user, rider)
    if not premium_access_context["premium_access"]:
        messages.error(
            request,
            _("Pro porovnání jezdců potřebuješ aktivní předplatné tohoto jezdce nebo trenérský přístup přes klub."),
        )
        return redirect("rider:detail", pk=pk)

    base_runs = list(
        RaceRun.objects.filter(rider=rider, is_beginner=False)
        .select_related("event", "event__organizer", "result")
        .order_by("-event__date", "round_type", "round_number", "id")
    )
    base_results = list(
        Result.objects.filter(rider_id=rider.uci_id, is_beginner=False)
        .select_related("event", "event__organizer")
        .order_by("-date", "-id")
    )
    kpi_period = _resolve_kpi_period(request.GET.get("years"))
    track_options = _build_track_options(base_results, base_runs, kpi_cutoff=kpi_period["cutoff"])
    selected_wheel = request.GET.get("wheel")
    if selected_wheel not in {"20", "24"}:
        selected_wheel = None
    selected_track = _resolve_selected_track(track_options, request.GET.get("track"))
    require_wheel_selection = False

    if selected_track is not None:
        selected_track_results = [result for result in base_results if ((result.event and result.event.organizer_id) or 0) == selected_track["id"]]
        selected_track_runs = [run for run in base_runs if ((run.event and run.event.organizer_id) or 0) == selected_track["id"]]
        timed_track_event_ids = {run.event_id for run in selected_track_runs if run.finish_time is not None and run.event_id}
        timed_track_results = [result for result in selected_track_results if result.event_id in timed_track_event_ids]
        timed_track_runs = [run for run in selected_track_runs if run.finish_time is not None]
        available_wheels = []
        if any(result.is_20 for result in timed_track_results) or any(run.is_20 is True for run in timed_track_runs):
            available_wheels.append({"value": "20", "label": '20"'})
        if any(not result.is_20 for result in timed_track_results) or any(run.is_20 is False for run in timed_track_runs):
            available_wheels.append({"value": "24", "label": '24"'})
        if selected_wheel is None and len(available_wheels) == 1:
            selected_wheel = available_wheels[0]["value"]
        elif selected_wheel is None and len(available_wheels) > 1:
            require_wheel_selection = True
    else:
        available_wheels = []

    base_track_stats = None if require_wheel_selection else _build_track_stats(
        rider,
        selected_track,
        base_results,
        base_runs,
        wheel=selected_wheel,
        kpi_cutoff=kpi_period["cutoff"],
        kpi_label=kpi_period["label"],
    )

    peer_context = _build_peer_context(rider, selected_track, selected_wheel, kpi_cutoff=kpi_period["cutoff"])
    opponent = None
    opponent_track_stats = None
    head_to_head = None
    opponent_id = request.GET.get("opponent")
    if opponent_id and selected_track is not None and selected_wheel in {"20", "24"}:
        opponent = next((item for item in peer_context["candidates"] if str(item.uci_id) == opponent_id), None)
        if opponent is not None:
            opponent_runs = list(
                RaceRun.objects.filter(rider=opponent, is_beginner=False)
                .select_related("event", "event__organizer", "result")
                .order_by("-event__date", "round_type", "round_number", "id")
            )
            opponent_results = list(
                Result.objects.filter(rider_id=opponent.uci_id, is_beginner=False)
                .select_related("event", "event__organizer")
                .order_by("-date", "-id")
            )
            opponent_track_stats = _build_track_stats(
                opponent,
                selected_track,
                opponent_results,
                opponent_runs,
                wheel=selected_wheel,
                kpi_cutoff=kpi_period["cutoff"],
                kpi_label=kpi_period["label"],
            )
            base_track_results = [
                result
                for result in base_results
                if ((result.event and result.event.organizer_id) or 0) == selected_track["id"] and _matches_wheel_filter(result, selected_wheel)
            ]
            base_track_runs = [
                run
                for run in base_runs
                if ((run.event and run.event.organizer_id) or 0) == selected_track["id"] and _matches_wheel_filter(run, selected_wheel)
            ]
            opponent_track_results = [
                result
                for result in opponent_results
                if ((result.event and result.event.organizer_id) or 0) == selected_track["id"] and _matches_wheel_filter(result, selected_wheel)
            ]
            opponent_track_runs = [
                run
                for run in opponent_runs
                if ((run.event and run.event.organizer_id) or 0) == selected_track["id"] and _matches_wheel_filter(run, selected_wheel)
            ]
            if kpi_period["cutoff"] is not None:
                base_track_results = [item for item in base_track_results if item.date and item.date >= kpi_period["cutoff"]]
                opponent_track_results = [item for item in opponent_track_results if item.date and item.date >= kpi_period["cutoff"]]
                base_track_runs = [item for item in base_track_runs if item.event and item.event.date and item.event.date >= kpi_period["cutoff"]]
                opponent_track_runs = [item for item in opponent_track_runs if item.event and item.event.date and item.event.date >= kpi_period["cutoff"]]
            head_to_head = _build_head_to_head(
                base_track_results,
                opponent_track_results,
                base_track_runs,
                opponent_track_runs,
            )

    data = {
        "rider": rider,
        "subscription": premium_access_context["active_subscription"],
        "trainer_club_subscription": premium_access_context["trainer_club_subscription"],
        "has_admin_access": premium_access_context["premium_access_via_admin"],
        "has_trainer_club_access": premium_access_context["premium_access_via_trainer_club"],
        "kpi_period": kpi_period,
        "kpi_period_options": KPI_PERIOD_OPTIONS,
        "track_options": track_options,
        "selected_track": selected_track,
        "available_wheels": available_wheels,
        "selected_wheel": selected_wheel,
        "require_wheel_selection": require_wheel_selection,
        "base_track_stats": base_track_stats,
        "opponent": opponent,
        "opponent_track_stats": opponent_track_stats,
        "compare_candidates": peer_context["candidates"],
        "head_to_head": head_to_head,
    }
    return render(request, "rider/rider-compare.html", data)



@login_required
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
                _("Automatické obnovování pro %(name)s bylo vypnuto.") % {'name': f"{subscription.rider.first_name} {subscription.rider.last_name}"}
            )
        elif action == "enable-renew":
            resume_rider_stats_subscription(subscription)
            messages.success(
                request,
                _("Automatické obnovování pro %(name)s bylo zapnuto.") % {'name': f"{subscription.rider.first_name} {subscription.rider.last_name}"}
            )
        elif action == "delete":
            rider_name = f"{subscription.rider.first_name} {subscription.rider.last_name}"
            subscription.delete()
            messages.success(
                request,
                _("Předplatné jezdce %(name)s bylo smazáno z přehledu.") % {'name': rider_name}
            )
        return redirect("user:subscriptions")

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


__all__ = [
    'rider_premium_stats_subscribe_view',
    'rider_premium_stats_view',
    'rider_premium_stats_pdf_view',
    'rider_compare_view',
    'rider_premium_subscriptions_view',
]
