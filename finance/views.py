from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.utils import timezone
from datetime import date, timedelta
import stripe
import logging
import csv
from django.conf import settings
from django.utils.translation import gettext as _
from django.core.cache import cache

from .func import calculate_stripe_fee, calculate_system_balance_total
from event.models import CreditTransaction
from event.credit import get_system_balance_components
from accounts.models import Account
from django.db.models import F
from rider.models import RiderStatsCharge, TrainerClubCharge, TrainerClubSubscription
from finance.models import SubscriptionInvoice
from finance.subscription_invoices import SubscriptionInvoiceService

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")

# Create your views here.

def _is_finance_admin(user):
    return user.is_authenticated and user.is_admin


@login_required(login_url="/login/")
@user_passes_test(_is_finance_admin, login_url="/login/")
def finance_admin(request):

    current_year = date.today().year
    SubscriptionInvoiceService().ensure_for_all()

    stripe_fee = calculate_stripe_fee(current_year)
    credit = calculate_system_balance_total()
    balance_components = get_system_balance_components()
    completed_credit_transactions = CreditTransaction.objects.filter(payment_complete=True)
    credit_transaction_summary = {
        "topup_total": completed_credit_transactions.filter(
            kind=CreditTransaction.Kind.TOPUP
        ).aggregate(total=Sum("amount"))["total"] or 0,
        "topup_count": completed_credit_transactions.filter(
            kind=CreditTransaction.Kind.TOPUP
        ).aggregate(count=Count("id"))["count"] or 0,
        "checkout_refund_total": completed_credit_transactions.filter(
            kind=CreditTransaction.Kind.CHECKOUT_REFUND
        ).aggregate(total=Sum("amount"))["total"] or 0,
        "checkout_refund_count": completed_credit_transactions.filter(
            kind=CreditTransaction.Kind.CHECKOUT_REFUND
        ).aggregate(count=Count("id"))["count"] or 0,
    }
    checkout_refunds = completed_credit_transactions.filter(
        kind=CreditTransaction.Kind.CHECKOUT_REFUND
    ).select_related(
        "user",
        "source_entry__event",
        "source_entry__rider",
    ).order_by("-transaction_date")

    # Caching těžkých výpočtů na 15 minut (900 sekund)
    # Klíč obsahuje rok, aby se data nemíchala při přelomu roku
    cache_key = f"finance_dashboard_stats_{current_year}"
    cached_stats = cache.get(cache_key)

    if not cached_stats:
        rider_stats_revenue = (
            RiderStatsCharge.objects.filter(
                payment_valid=True,
                transaction_date__year=current_year,
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )
        trainer_club_stats_revenue = (
            TrainerClubCharge.objects.filter(
                payment_valid=True,
                transaction_date__year=current_year,
                product=TrainerClubSubscription.PRODUCT_CLUB_STATS,
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )
        trainer_extended_revenue = (
            TrainerClubCharge.objects.filter(
                payment_valid=True,
                transaction_date__year=current_year,
                product=TrainerClubSubscription.PRODUCT_EXTENDED,
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )
        cached_stats = {
            "rider_stats_revenue": rider_stats_revenue,
            "trainer_club_stats_revenue": trainer_club_stats_revenue,
            "trainer_extended_revenue": trainer_extended_revenue,
        }
        cache.set(cache_key, cached_stats, 900)

    data={
        "credit":credit,
        "balance_components": balance_components,
        "stripe_fee": stripe_fee,
        "rider_stats_revenue": cached_stats["rider_stats_revenue"],
        "trainer_club_stats_revenue": cached_stats["trainer_club_stats_revenue"],
        "trainer_extended_revenue": cached_stats["trainer_extended_revenue"],
        "current_year": current_year,
        "subscription_invoices": SubscriptionInvoice.objects.select_related("user").order_by("-issue_date", "-created")[:100],
        "checkout_refunds": checkout_refunds[:100],
        "credit_transaction_summary": credit_transaction_summary,
    }

    if request.method == "POST" and "verify_payments" in request.POST:
        audit_logger.info(
            "finance_manual_credit_verification_started admin_user_id=%s",
            request.user.id,
        )
        # Manuální ověření plateb za poslední 2 dny
        two_days_ago = timezone.now() - timedelta(days=2)
        credit_transactions = CreditTransaction.objects.filter(
            payment_complete=False,
            transaction_date__gte=two_days_ago,
        )

        verified_count = 0
        for ct in credit_transactions:
            try:
                with transaction.atomic():
                    ct = CreditTransaction.objects.select_for_update().get(id=ct.id)
                    if ct.payment_complete:
                        continue
                    confirm = stripe.checkout.Session.retrieve(ct.transaction_id)
                    if confirm.get("payment_status") == "paid":
                        Account.objects.filter(id=ct.user.id).update(
                            credit=F("credit") + ct.amount
                        )
                        ct.payment_complete = True
                        ct.payment_intent = confirm.get("payment_intent")
                        ct.save()
                        verified_count += 1
                        logger.info(f"Manuálně ověřena platba kreditu: {ct}")
                        audit_logger.info(
                            "finance_credit_payment_verified admin_user_id=%s transaction_id=%s target_user_id=%s amount=%s",
                            request.user.id,
                            ct.id,
                            ct.user_id,
                            ct.amount,
                        )
            except Exception as e:
                logger.error(f"Chyba při manuálním ověření kreditu {ct.id}: {e}")
                audit_logger.exception(
                    "finance_credit_payment_verification_failed admin_user_id=%s transaction_id=%s",
                    request.user.id,
                    ct.id,
                )

        messages.success(request, _("Ověřeno %(count)d plateb za kredity za poslední 2 dny.") % {
            'count': verified_count
        })
        audit_logger.info(
            "finance_manual_credit_verification_finished admin_user_id=%s verified_count=%s",
            request.user.id,
            verified_count,
        )
        # Invalidace cache po manuální akci, aby byla čísla aktuální
        cache.delete(cache_key)
        # Aktualizovat data po ověření
        credit = calculate_system_balance_total()
        data["credit"] = credit
        data["balance_components"] = get_system_balance_components()

    return render(request, "finance/finance.html", data)


@login_required(login_url="/login/")
@user_passes_test(_is_finance_admin, login_url="/login/")
def export_checkout_refunds_csv(request):
    refunds = (
        CreditTransaction.objects.filter(
            payment_complete=True,
            kind=CreditTransaction.Kind.CHECKOUT_REFUND,
        )
        .select_related("user", "source_entry__event", "source_entry__rider")
        .order_by("-transaction_date")
    )

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="checkout-refunds.csv"'
    response.write("\ufeff")

    writer = csv.writer(response)
    writer.writerow(
        [
            _("Datum"),
            _("Uživatel"),
            _("Email"),
            _("Jezdec"),
            _("Závod"),
            _("Částka"),
            _("Payment intent"),
            _("Registrace ID"),
            _("Transaction ID"),
        ]
    )

    for refund in refunds:
        rider_name = ""
        event_name = ""
        entry_id = ""
        if refund.source_entry:
            rider_name = str(refund.source_entry.rider) if refund.source_entry.rider else ""
            event_name = refund.source_entry.event.name if refund.source_entry.event else ""
            entry_id = refund.source_entry_id

        writer.writerow(
            [
                timezone.localtime(refund.transaction_date).strftime("%d.%m.%Y %H:%M")
                if refund.transaction_date
                else "",
                str(refund.user) if refund.user else "",
                refund.user.email if refund.user and refund.user.email else "",
                rider_name,
                event_name,
                refund.amount,
                refund.payment_intent,
                entry_id,
                refund.transaction_id,
            ]
        )

    audit_logger.info(
        "finance_checkout_refunds_csv_exported admin_user_id=%s count=%s",
        request.user.id,
        refunds.count(),
    )
    return response
