import datetime
import logging
from datetime import date
from types import SimpleNamespace

import stripe
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone

from accounts.models import Account
from event.credit import calculate_user_balance
from event.models import CreditTransaction, DebetTransaction, Entry, EntryForeign
from rider.models import RiderStatsCharge, TrainerClubCharge
from event.services.payments import get_entry_amount


stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)


def _construct_stripe_event(payload, sig_header):
    webhook_secrets = [
        secret for secret in getattr(settings, "STRIPE_ENDPOINT_SECRETS", []) if secret
    ]
    if not webhook_secrets and getattr(settings, "STRIPE_ENDPOINT_SECRET", ""):
        webhook_secrets = [settings.STRIPE_ENDPOINT_SECRET]

    if not webhook_secrets:
        raise ValueError("Stripe webhook secret is not configured.")

    last_error = None
    for secret in webhook_secrets:
        try:
            return stripe.Webhook.construct_event(payload, sig_header, secret)
        except stripe.error.SignatureVerificationError as error:
            last_error = error

    if last_error:
        raise last_error
    raise ValueError("Stripe webhook signature verification failed.")


def _mark_credit_transaction_paid(credit_transaction, *, payment_intent=""):
    if credit_transaction.payment_complete:
        return False

    Account.objects.filter(id=credit_transaction.user.id).update(
        credit=F("credit") + credit_transaction.amount
    )
    credit_transaction.payment_complete = True
    if payment_intent:
        credit_transaction.payment_intent = payment_intent
        credit_transaction.save(update_fields=["payment_complete", "payment_intent"])
    else:
        credit_transaction.save(update_fields=["payment_complete"])
    return True


def _mark_entry_records_paid(entries, *, customer_details=None):
    customer_details = customer_details or {}
    updated = False
    for entry in entries:
        if entry.payment_complete:
            continue
        entry.payment_complete = True
        entry.customer_name = customer_details.get("name", "")
        entry.customer_email = customer_details.get("email", "")
        entry.save(update_fields=["payment_complete", "customer_name", "customer_email"])
        updated = True
    return updated


def finalize_entry_checkout_session(session_id, *, event_id=None, is_foreign=False):
    if not session_id:
        return False

    confirm = stripe.checkout.Session.retrieve(session_id)
    if confirm.get("payment_status") != "paid":
        return False

    model = EntryForeign if is_foreign else Entry
    customer_details = confirm.get("customer_details") or {}

    with transaction.atomic():
        entries = model.objects.select_for_update().filter(
            transaction_id=session_id,
            payment_complete=False,
        )
        if event_id is not None:
            entries = entries.filter(event_id=event_id)
        entries = list(entries)
        return _mark_entry_records_paid(entries, customer_details=customer_details)


def finalize_credit_transaction_by_session_id(session_id, *, user=None):
    if not session_id:
        return False

    confirm = stripe.checkout.Session.retrieve(session_id)
    if confirm.get("payment_status") != "paid":
        return False

    with transaction.atomic():
        credit_transactions = CreditTransaction.objects.select_for_update().filter(
            transaction_id=session_id
        )
        if user is not None:
            credit_transactions = credit_transactions.filter(user=user)
        credit_transaction = credit_transactions.first()
        if credit_transaction is None:
            return False
        return _mark_credit_transaction_paid(
            credit_transaction,
            payment_intent=confirm.get("payment_intent", ""),
        )


def handle_credit_webhook(payload, sig_header):
    try:
        stripe_event = _construct_stripe_event(payload, sig_header)
    except ValueError as error:
        logger.error(f"Invalid payload: {error}")
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as error:
        logger.error(f"Invalid signature: {error}")
        return HttpResponse(status=400)

    if stripe_event["type"] != "checkout.session.completed":
        return HttpResponse(status=200)

    session = stripe_event["data"]["object"]
    session_id = session["id"]
    payment_intent = session.get("payment_intent")
    payment_status = session.get("payment_status")
    customer_details = session.get("customer_details") or {}

    # Try to handle credit transaction
    try:
        with transaction.atomic():
            credit_transaction = CreditTransaction.objects.select_for_update().get(
                transaction_id=session_id
            )
            if payment_status == "paid" and _mark_credit_transaction_paid(
                credit_transaction,
                payment_intent=payment_intent,
            ):
                logger.info(
                    "[Webhook] Kredit přičten uživateli %s: +%s Kč",
                    credit_transaction.user.id,
                    credit_transaction.amount,
                )
        return HttpResponse(status=200)
    except CreditTransaction.DoesNotExist:
        pass  # Not a credit transaction, check for entries

    # Handle entry transactions
    try:
        with transaction.atomic():
            entries = Entry.objects.select_for_update().filter(
                transaction_id=session_id, payment_complete=False
            )
            entries = list(entries)
            if entries and payment_status == "paid":
                _mark_entry_records_paid(entries, customer_details=customer_details)
                logger.info(
                    "[Webhook] Přihlášky označeny jako zaplacené: %s",
                    [str(e) for e in entries]
                )
                return HttpResponse(status=200)
    except Exception as error:
        logger.error(f"[Webhook] Chyba při zpracování přihlášek: {error}")

    # Handle foreign entry transactions
    try:
        with transaction.atomic():
            entries = EntryForeign.objects.select_for_update().filter(
                transaction_id=session_id, payment_complete=False
            )
            entries = list(entries)
            if entries and payment_status == "paid":
                _mark_entry_records_paid(entries, customer_details=customer_details)
                logger.info(
                    "[Webhook] Zahraniční přihlášky označeny jako zaplacené: %s",
                    [str(e) for e in entries]
                )
                return HttpResponse(status=200)
    except Exception as error:
        logger.error(f"[Webhook] Chyba při zpracování zahraničních přihlášek: {error}")

    return HttpResponse(status=200)


def delete_expired_entries(user):
    delete_reg = Entry.objects.filter(
        user__id=user.id,
        payment_complete=False,
        event__reg_open_to__lt=timezone.now(),
    )
    deleted_any = delete_reg.exists()
    if deleted_any:
        delete_reg.delete()
    return deleted_any


def build_pending_orders(user):
    return Entry.objects.filter(
        user__id=user.id,
        payment_complete=False,
        event__date__gte=timezone.now(),
    ).select_related("event", "rider", "user").order_by(
        "event__date", "rider__last_name", "rider__first_name"
    )


def delete_order_from_cart(order_id, user):
    order = Entry.objects.get(id=order_id, user=user)
    order.delete()


def pay_orders_from_credit(*, user, orders):
    price = sum(get_entry_amount(order) for order in orders)
    if price > user.credit:
        return False

    with transaction.atomic():
        for order in orders:
            amount = get_entry_amount(order)
            DebetTransaction(user_id=user.id, amount=amount, entry=order).save()
            order.payment_complete = True
            order.save(update_fields=["payment_complete"])
        user.credit = calculate_user_balance(user.id)
        user.save(update_fields=["credit"])
    return True


def build_credit_checkout_line_item(user, amount):
    return (
        {
            "price_data": {
                "currency": "czk",
                "unit_amount": amount * 100,
                "product_data": {
                    "name": f"{user.first_name} {user.last_name}",
                    "images": [],
                    "description": "nabití kreditu pro registraci na závody BMX Racing",
                },
            },
            "quantity": 1,
        },
    )


def get_credit_history(user_id):
    credits = CreditTransaction.objects.filter(
        user__id=user_id,
        payment_complete=True,
        transaction_date__gte=timezone.now() - datetime.timedelta(days=365),
    ).order_by("-transaction_date")

    event_debets = DebetTransaction.objects.filter(
        user__id=user_id,
        transaction_date__gte=timezone.now() - datetime.timedelta(days=365),
    ).select_related("entry__event", "entry__rider")
    subscription_debets = RiderStatsCharge.objects.filter(
        user__id=user_id,
        transaction_date__gte=timezone.now() - datetime.timedelta(days=365),
    ).select_related("rider", "season", "subscription")
    trainer_subscription_debets = TrainerClubCharge.objects.filter(
        user__id=user_id,
        transaction_date__gte=timezone.now() - datetime.timedelta(days=365),
    ).select_related("club", "season", "subscription")

    debets = []

    for debet in event_debets:
        debets.append(
            SimpleNamespace(
                transaction_date=debet.transaction_date,
                amount=debet.amount,
                payment_valid=debet.payment_valid,
                description=str(debet.entry) if debet.entry else "Registrace na závod",
                debit_type="event_entry",
            )
        )

    for debet in subscription_debets:
        debets.append(
            SimpleNamespace(
                transaction_date=debet.transaction_date,
                amount=debet.amount,
                payment_valid=debet.payment_valid,
                description=(
                    f"Prémiové statistiky: {debet.rider.first_name} {debet.rider.last_name} "
                    f"({debet.get_reason_display().lower()})"
                    if debet.rider
                    else "Prémiové statistiky jezdce"
                ),
                debit_type="rider_stats_subscription",
            )
        )

    for debet in trainer_subscription_debets:
        debets.append(
            SimpleNamespace(
                transaction_date=debet.transaction_date,
                amount=debet.amount,
                payment_valid=debet.payment_valid,
                description=(
                    f"Trenérské předplatné: {debet.club.team_name} "
                    f"({debet.subscription.get_product_display().lower()}, {debet.get_reason_display().lower()})"
                    if debet.club and debet.subscription
                    else "Trenérské předplatné klubu"
                ),
                debit_type="trainer_club_subscription",
            )
        )

    debets.sort(key=lambda item: item.transaction_date or timezone.now(), reverse=True)
    return credits, debets


def finalize_pending_credit_transactions(user, *, session_id=""):
    if session_id:
        try:
            return finalize_credit_transaction_by_session_id(session_id, user=user)
        except CreditTransaction.DoesNotExist:
            return False
        except stripe.error.StripeError as error:
            logger.error(f"Stripe error v success_credit_view: {error}")
            return False
        except Exception as error:
            logger.error(f"Chyba v success_credit_view: {error}")
            return False

    today = date.today()
    credit_transactions = CreditTransaction.objects.filter(
        user=user,
        payment_complete=False,
        transaction_date__date__gte=today - datetime.timedelta(days=1),
    )

    for ct in credit_transactions:
        try:
            with transaction.atomic():
                ct = CreditTransaction.objects.select_for_update().get(id=ct.id)
                if ct.payment_complete:
                    continue
                confirm = stripe.checkout.Session.retrieve(ct.transaction_id)
                if confirm["payment_status"] == "paid":
                    _mark_credit_transaction_paid(
                        ct,
                        payment_intent=confirm.get("payment_intent", ""),
                    )
        except CreditTransaction.DoesNotExist:
            continue
        except stripe.error.StripeError as error:
            logger.error(f"Stripe error v success_credit_view: {error}")
        except Exception as error:
            logger.error(f"Chyba v success_credit_view: {error}")


def build_recalculate_balances_context():
    return {
        "status": "success",
        "title": "Kontrola kreditu",
        "message": "Stavy kreditů se právě překontrolovávají.",
        "detail": "Po dokončení uvidíte výsledek přepočtu všech aktivních účtů.",
    }
