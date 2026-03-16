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
from event.models import CreditTransaction, DebetTransaction, Entry
from rider.models import RiderStatsCharge
from event.services.payments import get_entry_amount


stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)


def handle_credit_webhook(payload, sig_header):
    try:
        stripe_event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_ENDPOINT_SECRET
        )
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

    try:
        with transaction.atomic():
            credit_transaction = CreditTransaction.objects.select_for_update().get(
                transaction_id=session_id
            )
            if not credit_transaction.payment_complete:
                Account.objects.filter(id=credit_transaction.user.id).update(
                    credit=F("credit") + credit_transaction.amount
                )
                credit_transaction.payment_complete = True
                credit_transaction.payment_intent = payment_intent
                credit_transaction.save()
                logger.info(
                    "[Webhook] Kredit přičten uživateli %s: +%s Kč",
                    credit_transaction.user.id,
                    credit_transaction.amount,
                )
    except CreditTransaction.DoesNotExist:
        logger.warning("[Webhook] Kreditní transakce s ID %s nenalezena", session_id)
    except Exception as error:
        logger.error(f"[Webhook] Chyba při zpracování kreditu: {error}")

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

    debets.sort(key=lambda item: item.transaction_date or timezone.now(), reverse=True)
    return credits, debets


def finalize_pending_credit_transactions(user):
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
                    ct.payment_complete = True
                    ct.payment_intent = confirm["payment_intent"]
                    ct.save()
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
