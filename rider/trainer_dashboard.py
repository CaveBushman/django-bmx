import csv
import datetime
import re
from statistics import mean, median

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from openpyxl import Workbook

from club.models import Club
from event.models import RaceRun, Result
from rider.models import Rider, TrainerClubSubscription
from rider.plates import display_plate
from rider.subscriptions import (
    cancel_trainer_club_subscription,
    get_active_trainer_extended_subscription,
    get_current_season_settings,
    has_active_trainer_club_extended_access,
    purchase_trainer_club_subscription,
    resume_trainer_club_subscription,
)


def _format_export_number(value, digits=2):
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def trainer_can_use_extended_exports(user, club, *, at_time=None):
    if user.is_authenticated and (user.is_admin or user.is_superuser or user.is_staff):
        return True
    return has_active_trainer_club_extended_access(user, club, at_time=at_time)


def get_exportable_trainer_club_or_403(user, club_id):
    club = get_object_or_404(Club, pk=club_id, is_active=True)
    if not trainer_can_use_extended_exports(user, club):
        raise PermissionDenied("Pro exporty klubu je potřeba aktivní trenérské extended předplatné.")
    return club


def get_club_riders_queryset(club):
    return (
        Rider.objects.filter(club=club, is_active=True, is_approved=True)
        .select_related("club")
        .order_by("last_name", "first_name")
    )


def build_club_riders_export_rows(club):
    rows = []
    for rider in get_club_riders_queryset(club):
        rows.append(
            {
                "uci_id": rider.uci_id,
                "first_name": rider.first_name,
                "last_name": rider.last_name,
                "class_20": rider.class_20,
                "class_24": rider.class_24,
                "plate": display_plate(rider.plate_text, rider.plate, fallback=""),
                "transponder_20": rider.transponder_20,
                "transponder_24": rider.transponder_24,
                "valid_licence": "Ano" if rider.valid_licence else "Ne",
                "email": rider.email,
                "phone": rider.phone,
            }
        )
    return rows


def build_club_kpi_export_rows(club):
    cutoff = timezone.localdate() - datetime.timedelta(days=2 * 365)
    rows = []
    for rider in get_club_riders_queryset(club):
        results_qs = Result.objects.filter(rider=rider, is_beginner=False).exclude(event__isnull=True)
        recent_results_qs = results_qs.filter(date__gte=cutoff)
        places = list(results_qs.exclude(place__lte=0).values_list("place", flat=True))
        finish_runs = RaceRun.objects.filter(
            rider=rider,
            result__is_beginner=False,
            finish_time__isnull=False,
        )
        hill_runs = RaceRun.objects.filter(
            rider=rider,
            result__is_beginner=False,
            hill_time__isnull=False,
        )
        split_runs = RaceRun.objects.filter(
            rider=rider,
            result__is_beginner=False,
            split_1__isnull=False,
        )

        finish_times = list(finish_runs.values_list("finish_time", flat=True))
        hill_times = list(hill_runs.values_list("hill_time", flat=True))
        split_times = list(split_runs.values_list("split_1", flat=True))

        rows.append(
            {
                "uci_id": rider.uci_id,
                "first_name": rider.first_name,
                "last_name": rider.last_name,
                "class_20": rider.class_20,
                "class_24": rider.class_24,
                "starts_total": results_qs.count(),
                "starts_last_2y": recent_results_qs.count(),
                "best_result": min(places) if places else None,
                "avg_place": _format_export_number(mean(places), 2) if places else "",
                "median_finish": _format_export_number(median(finish_times), 3) if finish_times else "",
                "best_finish": _format_export_number(min(finish_times), 3) if finish_times else "",
                "median_hill": _format_export_number(median(hill_times), 3) if hill_times else "",
                "median_split_1": _format_export_number(median(split_times), 3) if split_times else "",
            }
        )
    return rows


def export_rows_as_csv(filename, headers, rows):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response, delimiter=";")
    writer.writerow([label for _, label in headers])
    for row in rows:
        writer.writerow([row.get(key, "") for key, _ in headers])
    return response


def export_rows_as_xlsx(filename, sheet_name, headers, rows):
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name
    worksheet.append([label for _, label in headers])
    for row in rows:
        worksheet.append([row.get(key, "") for key, _ in headers])
    workbook.save(response)
    return response


def serialize_trainer_subscription(subscription, now):
    if not subscription:
        return {
            "label": "Bez předplatného",
            "is_active": False,
            "expires_at": None,
            "status": None,
            "auto_renew": False,
            "is_simulated": False,
            "subscription_id": None,
        }
    is_active = (
        subscription.status == TrainerClubSubscription.STATUS_ACTIVE
        and subscription.expires_at >= now
    )
    return {
        "label": subscription.get_status_display(),
        "is_active": is_active,
        "expires_at": subscription.expires_at,
        "status": subscription.status,
        "auto_renew": subscription.auto_renew,
        "is_simulated": False,
        "subscription_id": subscription.id,
    }


def build_trainer_dashboard_context(account):
    now = timezone.now()
    season_settings = get_current_season_settings()
    trainer_clubs = list(account.trainer_clubs.filter(is_active=True).order_by("team_name"))
    subscriptions = (
        TrainerClubSubscription.objects.filter(user=account, club__in=trainer_clubs)
        .select_related("club")
        .order_by("club__team_name", "product", "-expires_at")
    )

    latest_by_club_product = {}
    for subscription in subscriptions:
        key = (subscription.club_id, subscription.product)
        if key not in latest_by_club_product:
            latest_by_club_product[key] = subscription

    club_rows = []
    global_extended_subscription = get_active_trainer_extended_subscription(account, at_time=now)
    global_extended_info = serialize_trainer_subscription(global_extended_subscription, now)
    global_extended_info["requires_active_stats"] = True
    global_extended_info["has_required_stats"] = False
    global_extended_info["purchase_block_reason"] = None
    global_extended_info["can_purchase"] = getattr(account, "is_trainer", False) and not global_extended_info["is_active"]
    global_extended_info["can_disable_renew"] = global_extended_info["is_active"] and global_extended_info["auto_renew"]
    global_extended_info["can_enable_renew"] = global_extended_info["is_active"] and not global_extended_info["auto_renew"]

    active_stats_count = 0
    for club in trainer_clubs:
        stats_subscription = latest_by_club_product.get((club.id, TrainerClubSubscription.PRODUCT_CLUB_STATS))
        stats_info = serialize_trainer_subscription(stats_subscription, now)
        if stats_info["is_active"]:
            active_stats_count += 1
        extended_exports_enabled = trainer_can_use_extended_exports(account, club, at_time=now)
        stats_info["can_purchase"] = getattr(account, "is_trainer", False) and not stats_info["is_active"] and not stats_info["is_simulated"]
        stats_info["can_disable_renew"] = stats_info["is_active"] and stats_info["auto_renew"] and not stats_info["is_simulated"]
        stats_info["can_enable_renew"] = stats_info["is_active"] and not stats_info["auto_renew"] and not stats_info["is_simulated"]
        club_rows.append(
            {
                "club": club,
                "stats": stats_info,
                "extended_exports_enabled": extended_exports_enabled,
                "extended_exports_locked": stats_info["is_active"] and not extended_exports_enabled,
            }
        )

    global_extended_info["has_required_stats"] = active_stats_count > 0
    if global_extended_info["can_purchase"] and not global_extended_info["has_required_stats"]:
        global_extended_info["can_purchase"] = False
        global_extended_info["purchase_block_reason"] = "Extended lze aktivovat až po předplacení stats alespoň u jednoho klubu."

    return {
        "season_settings": season_settings,
        "trainer_clubs": club_rows,
        "trainer_clubs_count": len(club_rows),
        "active_stats_count": active_stats_count,
        "global_extended_info": global_extended_info,
        "can_manage_trainer_subscriptions": getattr(account, "is_trainer", False),
    }


def handle_trainer_dashboard_post(request):
    account = request.user
    action = request.POST.get("action")

    if action == "purchase-extended":
        anchor_club = account.trainer_clubs.filter(is_active=True).order_by("team_name").first()
        if anchor_club is None:
            messages.error(request, "Pro rozšířené trenérské předplatné musí být k účtu přiřazený alespoň jeden aktivní klub.")
        else:
            try:
                subscription, created = purchase_trainer_club_subscription(
                    account,
                    club=anchor_club,
                    product=TrainerClubSubscription.PRODUCT_EXTENDED,
                )
            except ValueError as error:
                messages.error(request, str(error))
            else:
                if created:
                    messages.success(
                        request,
                        f"Rozšířené trenérské předplatné je aktivní do {timezone.localtime(subscription.expires_at):%d.%m.%Y %H:%M}.",
                    )
                else:
                    messages.info(request, "Rozšířené trenérské předplatné už máš aktivní.")
        return redirect("rider:trainer-dashboard")

    if action in {"disable-extended-renew", "enable-extended-renew"}:
        subscription = get_object_or_404(
            TrainerClubSubscription,
            pk=request.POST.get("subscription_id"),
            user=account,
            product=TrainerClubSubscription.PRODUCT_EXTENDED,
        )
        if action == "disable-extended-renew":
            cancel_trainer_club_subscription(subscription)
            messages.success(request, "Automatické obnovování rozšířeného trenérského předplatného bylo vypnuto.")
        else:
            resume_trainer_club_subscription(subscription)
            messages.success(request, "Automatické obnovování rozšířeného trenérského předplatného bylo zapnuto.")
        return redirect("rider:trainer-dashboard")

    if action == "purchase-stats":
        club = get_object_or_404(Club, pk=request.POST.get("club_id"), is_active=True)
        try:
            subscription, created = purchase_trainer_club_subscription(
                account,
                club=club,
                product=TrainerClubSubscription.PRODUCT_CLUB_STATS,
            )
        except ValueError as error:
            messages.error(request, str(error))
        else:
            if created:
                messages.success(
                    request,
                    f"Klubové stats pro {club.team_name} jsou aktivní do {timezone.localtime(subscription.expires_at):%d.%m.%Y %H:%M}.",
                )
            else:
                messages.info(request, f"Klubové stats pro {club.team_name} už máš aktivní.")
        return redirect("rider:trainer-dashboard")

    if action in {"disable-stats-renew", "enable-stats-renew"}:
        subscription = get_object_or_404(
            TrainerClubSubscription.objects.select_related("club"),
            pk=request.POST.get("subscription_id"),
            user=account,
            product=TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )
        if action == "disable-stats-renew":
            cancel_trainer_club_subscription(subscription)
            messages.success(request, f"Automatické obnovování stats pro {subscription.club.team_name} bylo vypnuto.")
        else:
            resume_trainer_club_subscription(subscription)
            messages.success(request, f"Automatické obnovování stats pro {subscription.club.team_name} bylo zapnuto.")
        return redirect("rider:trainer-dashboard")

    return None


def build_trainer_export_filename(club, suffix):
    slug = re.sub(r"[^a-z0-9]+", "-", club.team_name.lower()).strip("-") or f"club-{club.id}"
    return f"{slug}-{suffix}"
