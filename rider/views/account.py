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
from rider.rider import extract_licence_identity, get_rider_data
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
def account_settings_invoices_view(request):
    AvatarChangeRequest.expire_stale_requests()
    if request.method == "POST" and request.POST.get("action") == "submit-avatar-request":
        return submit_avatar_change_request_view(request)

    SubscriptionInvoiceService().ensure_for_user(request.user)
    invoices_qs = (
        SubscriptionInvoice.objects.filter(user=request.user)
        .order_by("-issue_date", "-created")
    )
    invoices_count = invoices_qs.count()
    invoices_page_obj = None
    if invoices_count > 25:
        invoices_page_obj = Paginator(invoices_qs, 25).get_page(request.GET.get("invoice_page"))
        invoices = list(invoices_page_obj.object_list)
    else:
        invoices = list(invoices_qs)
    individual_subscriptions = (
        RiderStatsSubscription.objects.filter(user=request.user)
        .select_related("rider")
        .order_by("-expires_at", "rider__last_name", "rider__first_name")[:5]
    )
    linked_riders = list(
        request.user.riders.select_related("club")
        .filter(is_active=True)
        .order_by("last_name", "first_name")
    )
    account_avatar_request_pending = _get_pending_avatar_request_for_target(account=request.user) is not None
    linked_rider_pending_request_ids = {
        request_obj.target_rider_id
        for request_obj in AvatarChangeRequest.objects.filter(
            status=AvatarChangeRequest.STATUS_PENDING,
            target_rider__in=linked_riders,
        ).only("target_rider_id")
    }
    trainer_subscriptions = (
        TrainerClubSubscription.objects.filter(user=request.user)
        .select_related("club")
        .order_by("-expires_at", "club__team_name")[:8]
    )
    subscriptions_summary_count = len(individual_subscriptions) + len(trainer_subscriptions)
    club_event_invoices = []
    club_event_invoices_count = 0
    club_event_invoices_page_obj = None
    managed_club = None
    if getattr(request.user, "is_club_manager", False) and request.user.club_id:
        managed_club = request.user.club
        club_event_invoices_qs = (
            EventInvoice.objects.filter(club=request.user.club)
            .select_related("event", "club")
            .order_by("-issue_date", "-created")
        )
        club_event_invoices_count = club_event_invoices_qs.count()
        if club_event_invoices_count > 25:
            club_event_invoices_page_obj = Paginator(club_event_invoices_qs, 25).get_page(
                request.GET.get("club_invoice_page")
            )
            club_event_invoices = list(club_event_invoices_page_obj.object_list)
        else:
            club_event_invoices = list(club_event_invoices_qs)
    return render(
        request,
        "rider/account-settings-invoices.html",
        {
            "invoices": invoices,
            "invoices_count": invoices_count,
            "invoices_page_obj": invoices_page_obj,
            "individual_subscriptions": individual_subscriptions,
            "linked_riders": linked_riders,
            "linked_riders_count": len(linked_riders),
            "account_avatar_request_pending": account_avatar_request_pending,
            "linked_rider_pending_request_ids": linked_rider_pending_request_ids,
            "trainer_subscriptions": trainer_subscriptions,
            "subscriptions_summary_count": subscriptions_summary_count,
            "can_manage_inactive_riders": can_manage_inactive_riders(request.user),
            "managed_club": managed_club,
            "club_event_invoices": club_event_invoices,
            "club_event_invoices_count": club_event_invoices_count,
            "club_event_invoices_page_obj": club_event_invoices_page_obj,
            "mobile_app_subscription": get_active_mobile_app_subscription(request.user),
        },
    )



@login_required
def submit_avatar_change_request_view(request):
    if request.method != "POST":
        return redirect("user:account")

    AvatarChangeRequest.expire_stale_requests()

    uploaded_file = request.FILES.get("avatar_image")
    target_type = request.POST.get("target_type")
    target_id = request.POST.get("target_id")

    try:
        _validate_avatar_upload(uploaded_file)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("user:account")

    if target_type == "account":
        if str(request.user.pk) != str(target_id):
            messages.error(request, _("Nemůžeš žádat změnu avataru pro jiný účet."))
            return redirect("user:account")
        pending_request = _get_pending_avatar_request_for_target(account=request.user)
        if pending_request:
            messages.error(request, _("Pro tvůj účet už čeká jedna žádost o změnu avataru na schválení."))
            return redirect("user:account")
        AvatarChangeRequest.objects.create(
            uploaded_by=request.user,
            target_account=request.user,
            image=uploaded_file,
        )
        messages.success(request, _("Nový avatar účtu byl odeslán ke schválení administrátorem."))
        return redirect("user:account")

    if target_type == "rider":
        rider = request.user.riders.filter(pk=target_id, is_active=True).first()
        if not rider:
            messages.error(request, _("Nemůžeš žádat změnu avataru pro cizího jezdce."))
            return redirect("user:account")
        pending_request = _get_pending_avatar_request_for_target(rider=rider)
        if pending_request:
            messages.error(request, _("Pro tohoto jezdce už čeká jedna žádost o změnu avataru na schválení."))
            return redirect("user:account")
        AvatarChangeRequest.objects.create(
            uploaded_by=request.user,
            target_rider=rider,
            image=uploaded_file,
        )
        messages.success(
            request,
            _("Nový avatar pro jezdce %(name)s byl odeslán ke schválení administrátorem.")
            % {"name": f"{rider.first_name} {rider.last_name}"},
        )
        return redirect("user:account")

    messages.error(request, _("Neplatný cíl změny avataru."))
    return redirect("user:account")



def rider_new_view(request):
    if request.method == "POST":
        context = dict(
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

        protection_error = protect_public_flow("rider_request", request)
        if protection_error is not None:
            logger.warning(
                "rider_request_rejected_%s ip=%s",
                protection_error["reason"],
                request.META.get("REMOTE_ADDR", ""),
            )
            messages.error(request, protection_error["message"])
            return _render_rider_request(request, context, status=protection_error["status"])

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
                messages.error(request, _("Pole %(label)s je povinné.") % {'label': label})
                return _render_rider_request(request, context)

        if request.POST.get("lookup_confirmed") != "1":
            messages.error(request, _("Nejprve ověř UCI ID proti licenci ČSC."))
            return _render_rider_request(request, context)

        uci_id = request.POST["uci_id"].strip()
        if not uci_id.isdigit() or len(uci_id) != 11:
            messages.error(request, _("UCI ID musí obsahovat přesně 11 číslic."))
            return _render_rider_request(request, context)

        if request.POST.get("gender") not in {"Muž", "Žena", "Ostatní"}:
            messages.error(request, _("Vyber platnou hodnotu pohlaví."))
            return _render_rider_request(request, context)

        existing = Rider.objects.filter(uci_id=uci_id).first()
        if existing:
            messages.error(
                request,
                _("Jezdec/jezdkyně %(name)s, UCI ID %(uci_id)s, již má přidělené číslo.") % {'name': f"{existing.first_name} {existing.last_name}", 'uci_id': uci_id}
            )
            return _render_rider_request(request, context)

        data_json, error_msg = get_rider_data(uci_id)
        if error_msg or not data_json:
            if error_msg and "nebyla nalezena" in error_msg:
                message = _("Licence UCI ID nebyla nalezena.")
            elif error_msg and "chyba záznamu" in error_msg:
                message = _(
                    "ČSC vrací u tohoto UCI ID chybu záznamu, i když licence je platná. "
                    "Jezdce nelze přidat automaticky – přidej ho prosím přes administraci "
                    "nebo kontaktuj správce."
                )
            else:
                message = _("Údaje licence se nepodařilo načíst z ČSC. Zkus to prosím později.")
            messages.error(request, message)
            return _render_rider_request(request, context)

        identity = extract_licence_identity(data_json)
        if identity is None:
            messages.error(
                request,
                _("ČSC vrátilo neúplné údaje licence. Bez jména, příjmení, data narození a pohlaví nelze pokračovat."),
            )
            return _render_rider_request(request, context)

        if "is20" not in request.POST and "is24" not in request.POST:
            messages.error(request, _('Musíš vybrat, zda budeš jezdit 20" nebo 24" kolo.'))
            return _render_rider_request(request, context)

        try:
            date_of_birth = datetime.datetime.strptime(
                identity["date_of_birth"], "%Y-%m-%d"
            )
        except (TypeError, ValueError):
            messages.error(request, _("Datum narození není ve správném formátu."))
            return _render_rider_request(request, context)

        club = Club.objects.filter(id=request.POST.get("club")).first()
        if not club:
            messages.error(request, _("Vybraný klub nebyl nalezen."))
            return _render_rider_request(request, context)

        club = Club.objects.filter(id=request.POST.get("club")).first()
        if club is None:
            messages.error(request, _("Vybraný klub nebyl nalezen."))
            return render(request, "rider/rider-request.html", context)

        Rider.objects.create(
            first_name=identity["first_name"],
            last_name=identity["last_name"],
            date_of_birth=date_of_birth,
            gender=identity["gender"],
            uci_id=uci_id,
            is_20="is20" in request.POST,
            is_24="is24" in request.POST,
            is_elite="elite" in request.POST,
            plate_text=normalize_plate_value(request.POST["plate"]),
            plate=legacy_plate_int(request.POST["plate"]),
            club=club,
            is_active=True,
            is_approved=False,
            emergency_contact=request.POST["emergency-contact"],
            emergency_phone=request.POST["emergency-phone"],
        )
        return render(request, "rider/rider-request-success.html")

    return _render_rider_request(request)



@login_required
def mobile_app_subscription_view(request):
    """Správa ročního předplatného mobilní aplikace — aktivace, zrušení, obnovení."""
    if request.method == "POST":
        action = request.POST.get("action")
        promo_code = request.POST.get("promo_code", "").strip() or None

        if action == "activate":
            try:
                subscription, created = purchase_mobile_app_subscription(
                    request.user, promo_code_str=promo_code
                )
                if created:
                    messages.success(
                        request,
                        _("Mobilní aplikace aktivována do %(date)s.") % {
                            "date": timezone.localtime(subscription.expires_at).strftime("%d.%m.%Y")
                        },
                    )
                else:
                    messages.info(request, _("Předplatné mobilní aplikace je již aktivní."))
            except ValueError as exc:
                messages.error(request, str(exc))

        elif action == "cancel":
            sub = get_active_mobile_app_subscription(request.user)
            if sub:
                cancel_mobile_app_subscription(sub)
                messages.success(request, _("Automatické obnovení předplatného bylo vypnuto."))
            else:
                messages.error(request, _("Nemáš aktivní předplatné."))

        elif action == "resume":
            sub = (
                MobileAppSubscription.objects.filter(
                    user=request.user,
                    status__in=[MobileAppSubscription.STATUS_ACTIVE, MobileAppSubscription.STATUS_PAST_DUE],
                )
                .order_by("-expires_at")
                .first()
            )
            if sub:
                resume_mobile_app_subscription(sub)
                messages.success(request, _("Automatické obnovení předplatného bylo zapnuto."))
            else:
                messages.error(request, _("Nemáš předplatné k obnovení."))

        return redirect("user:subscription-mobile")

    season = get_current_season_settings()
    subscription = get_active_mobile_app_subscription(request.user)
    annual_price = season.mobile_app_annual_price if season else 0

    return render(request, "rider/mobile-app-subscription.html", {
        "subscription": subscription,
        "annual_price": annual_price,
        "balance": request.user.credit,
        "has_enough_credit": request.user.credit >= annual_price,
    })



@staff_member_required
def promo_codes_admin_view(request):
    from rider.models import PromoCode, PromoCodeUsage

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "generate":
            product = request.POST.get("product", PromoCode.PRODUCT_MOBILE_APP)
            discount_type = request.POST.get("discount_type", PromoCode.DISCOUNT_FREE)
            try:
                discount_value = int(request.POST.get("discount_value", 100))
            except (ValueError, TypeError):
                discount_value = 100
            max_uses_raw = request.POST.get("max_uses", "").strip()
            max_uses = int(max_uses_raw) if max_uses_raw.isdigit() else None

            import datetime as _dt
            from django.utils.dateparse import parse_date

            def _parse_date_field(field_name, end_of_day=False):
                raw = request.POST.get(field_name, "").strip()
                if not raw:
                    return None
                parsed = parse_date(raw)
                if not parsed:
                    return None
                t = _dt.time(23, 59, 59) if end_of_day else _dt.time(0, 0, 0)
                return timezone.make_aware(_dt.datetime.combine(parsed, t))

            # Rychlý preset (počet dní od teď) má přednost před ručním zadáním
            preset_days_raw = request.POST.get("preset_days", "").strip()
            if preset_days_raw.isdigit():
                preset_days = int(preset_days_raw)
                valid_from = timezone.now()
                valid_until = valid_from + _dt.timedelta(days=preset_days)
            else:
                valid_from = _parse_date_field("valid_from", end_of_day=False)
                valid_until = _parse_date_field("valid_until", end_of_day=True)

            note = request.POST.get("description", "").strip()

            promo = PromoCode.objects.create(
                product=product,
                discount_type=discount_type,
                discount_value=discount_value,
                max_uses=max_uses,
                valid_from=valid_from,
                valid_until=valid_until,
                description=note,
                created_by=request.user,
            )
            messages.success(request, _("Vygenerován promo kód: %(code)s") % {"code": promo.code})

        elif action == "deactivate":
            pk = request.POST.get("promo_id")
            PromoCode.objects.filter(pk=pk).update(is_active=False)
            messages.success(request, _("Promo kód byl deaktivován."))

        elif action == "activate":
            pk = request.POST.get("promo_id")
            PromoCode.objects.filter(pk=pk).update(is_active=True)
            messages.success(request, _("Promo kód byl aktivován."))

        elif action == "expire":
            pk = request.POST.get("promo_id")
            PromoCode.objects.filter(pk=pk).update(valid_until=timezone.now())
            messages.success(request, _("Platnost promo kódu byla okamžitě zrušena."))

        elif action == "delete":
            pk = request.POST.get("promo_id")
            promo = PromoCode.objects.filter(pk=pk).first()
            if promo:
                code = promo.code
                promo.delete()
                messages.success(request, _("Promo kód %(code)s byl smazán.") % {"code": code})

        elif action == "send_email":
            from bmx.email import send_html_email
            from django.urls import reverse as _reverse
            pk = request.POST.get("promo_id")
            recipient_email = request.POST.get("recipient_email", "").strip()
            promo = PromoCode.objects.filter(pk=pk).first()
            if not promo:
                messages.error(request, _("Promo kód nenalezen."))
            elif not recipient_email:
                messages.error(request, _("Zadej e-mailovou adresu příjemce."))
            else:
                product_label = promo.get_product_display()
                if promo.discount_type == PromoCode.DISCOUNT_FREE:
                    discount_text = _("Zdarma (100 % sleva)")
                elif promo.discount_type == PromoCode.DISCOUNT_PERCENT:
                    discount_text = f"{promo.discount_value} % sleva"
                else:
                    discount_text = f"Sleva {promo.discount_value} Kč"
                valid_until_str = (
                    timezone.localtime(promo.valid_until).strftime("%d.%m.%Y")
                    if promo.valid_until else ""
                )
                subject = f"Promo kód Czech BMX – {product_label}"
                try:
                    send_html_email(
                        subject=subject,
                        template="emails/promo_code.html",
                        context={
                            "promo_code": promo.code,
                            "product_label": product_label,
                            "discount_text": discount_text,
                            "valid_until": valid_until_str,
                            "subscription_url": request.build_absolute_uri(
                                _reverse("user:subscription-mobile")
                            ),
                        },
                        to=[recipient_email],
                    )
                    messages.success(request, _("Promo kód byl odeslán na %(email)s.") % {"email": recipient_email})
                except Exception as exc:
                    messages.error(request, _("Odeslání e-mailu selhalo: %(err)s") % {"err": str(exc)})

        return redirect("rider:promo-codes")

    # Filtrace
    filter_product = request.GET.get("product", "")
    filter_status = request.GET.get("status", "")
    filter_q = request.GET.get("q", "").strip()

    promo_qs = (
        PromoCode.objects.select_related("created_by")
        .prefetch_related("usages")
        .order_by("-created")
    )
    if filter_product:
        promo_qs = promo_qs.filter(product=filter_product)
    if filter_status == "active":
        promo_qs = promo_qs.filter(is_active=True)
    elif filter_status == "inactive":
        promo_qs = promo_qs.filter(is_active=False)
    if filter_q:
        promo_qs = promo_qs.filter(code__icontains=filter_q) | promo_qs.filter(description__icontains=filter_q)

    from accounts.models import Account
    users_with_email = (
        Account.objects.filter(is_active=True, email__isnull=False)
        .exclude(email="")
        .order_by("last_name", "first_name")
        .values("id", "first_name", "last_name", "email")
    )

    return render(request, "rider/promo-codes-admin.html", {
        "promo_codes": promo_qs,
        "product_choices": PromoCode.PRODUCT_CHOICES,
        "discount_choices": PromoCode.DISCOUNT_CHOICES,
        "users_with_email": users_with_email,
        "filter_product": filter_product,
        "filter_status": filter_status,
        "filter_q": filter_q,
    })



@login_required
def redeem_promo_code_view(request):
    """Uplatnění promo kódu uživatelem (vstupní bod je na stránce dobíjení kreditu,
    event:credit) — přidá kredit nebo přesměruje na aktivaci předplatného."""
    from rider.promo_codes import redeem_credit_promo_code
    from rider.models import PromoCode

    # Vstupní formulář žije na stránce kreditu; GET sem jen přesměruje zpět.
    if request.method != "POST":
        return redirect("event:credit")

    code_str = request.POST.get("code", "").strip().upper()
    if not code_str:
        messages.error(request, _("Zadej promo kód."))
        return redirect("event:credit")

    try:
        promo = PromoCode.objects.get(code=code_str)
    except PromoCode.DoesNotExist:
        messages.error(request, _("Promo kód neexistuje."))
        return redirect("event:credit")

    if promo.discount_type == PromoCode.DISCOUNT_CREDIT:
        try:
            amount, _ok = redeem_credit_promo_code(request.user, code_str)
            messages.success(
                request,
                _("Promo kód uplatněn — na váš účet bylo připsáno %(amount)s Kč kreditu.") % {"amount": amount}
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect("event:credit")

    # Kód slouží ke slevě na předplatné — přesměruj na aktivaci
    if promo.product == PromoCode.PRODUCT_MOBILE_APP or promo.product == PromoCode.PRODUCT_ALL:
        return redirect(f"{reverse('user:subscription-mobile')}?promo={code_str}")

    messages.info(request, _("Kód je platný. Zadej ho při aktivaci příslušného předplatného."))
    return redirect("user:account")


__all__ = [
    'account_settings_invoices_view',
    'submit_avatar_change_request_view',
    'rider_new_view',
    'mobile_app_subscription_view',
    'promo_codes_admin_view',
    'redeem_promo_code_view',
]
