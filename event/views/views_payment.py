"""
event/views/views_payment.py — Stripe platby, kredit, správa objednávek

Obsah: success/cancel Stripe flow, webhook pro kredit, košík (order),
       kredit pro jezdce, přepočet zůstatků.
"""

import logging
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.conf import settings
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from event.models import Entry, CreditTransaction, DebetTransaction
from accounts.models import Account
from event.func import update_cart, is_registration_open
from event.credit import calculate_user_balance, recalculate_all_balances
from event.services.payments import (
    clear_checkout_session,
    enrich_cart_entries,
    get_recent_pending_entries,
    mark_entry_paid,
    remove_conflicting_cart_entries,
)
from event.views.payment_helpers import (
    build_credit_checkout_line_item,
    build_pending_orders,
    build_recalculate_balances_context,
    delete_expired_entries,
    delete_order_from_cart,
    finalize_credit_transaction_by_session_id,
    finalize_entry_checkout_session,
    finalize_pending_credit_transactions,
    get_credit_history,
    handle_credit_webhook,
    pay_orders_from_credit,
)
import stripe

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")


def _sum_order_amount(orders):
    return sum(
        getattr(order, "fee_beginner", 0) + getattr(order, "fee_20", 0) + getattr(order, "fee_24", 0)
        for order in orders
    )


def success_view(request, pk):
    """Stripe success redirect — označí zaplacené přihlášky jako dokončené.

    Kontroluje transakce z dnešního a včerejšího dne (pro případ přechodu půlnoci).
    """
    session_id = request.GET.get("session_id", "")
    if session_id:
        try:
            finalize_entry_checkout_session(session_id, event_id=pk)
        except Exception as e:
            logger.error(f"Chyba při zpracování transakce {session_id}: {e}")
    else:
        transactions = get_recent_pending_entries(event_id=pk)

        for t in transactions:
            try:
                confirm = stripe.checkout.Session.retrieve(t.transaction_id)
                mark_entry_paid(t, confirm)
            except Exception as e:
                logger.error(f"Chyba při zpracování transakce: {e}")

    try:
        clear_checkout_session(request)
    except Exception as e:
        logger.error(f"Chyba při mazání session: {e}")

    return render(request, "event/success.html", {"event_id": pk})


def cancel_view(request):
    """Stripe cancel redirect — vrať uživatele na správný krok flow."""
    source = (request.GET.get("source") or "").strip().lower()
    event_id = request.GET.get("event_id", "").strip()

    if source == "entries":
        messages.info(
            request,
            "Platba byla ve Stripe zrušena. Přihlášky zůstaly připravené a můžeš je znovu potvrdit.",
        )
        return redirect("event:confirm")

    if source == "credit":
        messages.info(
            request,
            "Dobití kreditu bylo ve Stripe zrušeno. Můžeš upravit částku a platbu zkusit znovu.",
        )
        return redirect("event:credit")

    if source == "foreign" and event_id.isdigit():
        messages.info(
            request,
            "Platba zahraničních přihlášek byla ve Stripe zrušena. Souhrn zůstal zachovaný a můžeš pokračovat znovu.",
        )
        return redirect("event:entry-foreign-summary", pk=int(event_id))

    return render(request, "event/cancel.html")


@csrf_exempt
def stripe_credit_webhook(request):
    """Stripe webhook — zpracuje platbu kreditní transakce.

    Ověří podpis webhooku (Stripe-Signature), pak přičte kredit uživateli.
    select_for_update() zabrání dvojímu přičtení při paralelních webhookách.
    """
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    return handle_credit_webhook(payload, sig_header)


@login_required(login_url="/login/")
def confirm_user_order(request):
    """Košík — přehled nezaplacených přihlášek a platba z kreditu.

    GET: Zobrazí přihlášky v košíku, odstraní propadlé a duplicitní.
    POST (btn-del): Smaže konkrétní přihlášku z košíku.
    POST (submit): Zaplatí přihlášky z kreditu uživatele.
    """
    update_cart(request)

    if delete_expired_entries(request.user):
        return redirect("event:order")

    orders = build_pending_orders(request.user)

    duplicities = remove_conflicting_cart_entries(orders)

    if duplicities:
        logger.warning(f"Duplicitní položky v košíku: {duplicities}")
        return render(request, "event/order.html", {"duplicities": duplicities})

    if "btn-del" in request.POST:
        deleted_order_id = request.POST["btn-del"]
        delete_order_from_cart(deleted_order_id, request.user)
        audit_logger.info(
            "cart_order_deleted user_id=%s order_id=%s",
            request.user.id,
            deleted_order_id,
        )
        update_cart(request)
        return redirect("event:order")

    if request.POST:
        user = Account.objects.get(id=request.user.id)
        if not pay_orders_from_credit(user=user, orders=orders):
            audit_logger.warning(
                "cart_credit_checkout_rejected user_id=%s items=%s total_amount=%s current_credit=%s",
                request.user.id,
                orders.count(),
                _sum_order_amount(orders),
                user.credit,
            )
            messages.error(
                request,
                "Pro dokončení registrace nemáte dostatečný kredit. Dobijte kredit nebo smažte některou z registrací v košíku.",
            )
            return redirect("event:order")
        audit_logger.info(
            "cart_credit_checkout_confirmed user_id=%s items=%s total_amount=%s",
            request.user.id,
            orders.count(),
            _sum_order_amount(orders),
        )
        update_cart(request)
        return redirect("event:checkout")

    price = enrich_cart_entries(orders)

    data = {"orders": orders, "price": price, "sum": orders.count()}
    return render(request, "event/order.html", data)


@login_required(login_url="/login")
def check_order_payments(request):
    """Ověří stav platby nezaplacených přihlášek přes Stripe API."""
    session_id = request.GET.get("session_id", "")
    if session_id:
        try:
            finalize_entry_checkout_session(session_id)
        except (stripe.error.StripeError, Exception) as e:
            logger.error(f"Chyba při ověřování transakce: {e}")
    else:
        transactions = get_recent_pending_entries()

        for t in transactions:
            try:
                confirm = stripe.checkout.Session.retrieve(t.transaction_id)
                mark_entry_paid(t, confirm)
            except (stripe.error.StripeError, Exception) as e:
                logger.error(f"Chyba při ověřování transakce: {e}")

    update_cart(request)
    messages.success(request, "Vaše přihláška byla úspěšně přijata.")
    return render(request, "event/success.html", {})


@login_required(login_url="/login/")
def checkout_view(request):
    """Přehled zaplacených přihlášek uživatele s možností stornování."""
    user_id = request.user.id
    user = Account.objects.get(id=user_id)
    confirmed_events = Entry.objects.filter(
        user__id=user_id, payment_complete=True, event__date__gte=timezone.now(),
    ).order_by("event__date", "rider__last_name", "rider__first_name")

    for entry in confirmed_events:
        entry.is_visible = is_registration_open(entry.event)

    if "btn-change" in request.POST:
        # Storno přihlášky — smaž Entry a příslušné debetní transakce
        entry = Entry.objects.filter(id=request.POST["btn-change"], user=user).first()
        if entry:
            audit_logger.info(
                "confirmed_entry_deleted user_id=%s entry_id=%s event_id=%s",
                user.id,
                entry.id,
                entry.event_id,
            )
            DebetTransaction.objects.filter(user=user, entry=entry).delete()
            entry.delete()
        user.credit = calculate_user_balance(user.id)
        user.save()
        return redirect("event:checkout")

    data = {"confirmed_events": confirmed_events, "user": user}
    return render(request, "event/event-checkout.html", data)


@login_required(login_url="/login")
def credit_view(request):
    """Nákup kreditu přes Stripe — uloží CreditTransaction a přesměruje na platbu.

    GET: Přehled kreditních transakcí a debetů za posledních 365 dní.
    POST: Vytvoří Stripe Checkout session pro nákup kreditu (100–10 000 Kč).
    """
    user_id = request.user.id
    user = Account.objects.get(id=user_id)

    if request.POST:
        try:
            amount = int(request.POST["price"])
        except (ValueError, KeyError):
            messages.error(request, "Neplatná částka.")
            return redirect("event:credit")

        if amount < 100:
            messages.error(request, "Minimální částka pro nákup kreditu je 100 Kč.")
            return redirect("event:credit")

        if amount > 10000:
            messages.error(request, "Maximální částka pro nákup kreditu je 10 000 Kč.")
            return redirect("event:credit")

        line_item = build_credit_checkout_line_item(user, amount)

        try:
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=line_item,
                mode="payment",
                success_url=(
                    settings.YOUR_DOMAIN
                    + "/event/success-credit?session_id={CHECKOUT_SESSION_ID}"
                ),
                cancel_url=settings.YOUR_DOMAIN + "/event/cancel?source=credit",
            )
            CreditTransaction(
                transaction_id=checkout_session.id, amount=amount, user_id=user_id
            ).save()
            audit_logger.info(
                "credit_checkout_started user_id=%s amount=%s session_id=%s",
                user_id,
                amount,
                checkout_session.id,
            )
            return redirect(checkout_session.url, code=303)
        except Exception as e:
            audit_logger.exception(
                "credit_checkout_failed user_id=%s amount=%s",
                user_id,
                amount,
            )
            return JsonResponse({'error': str(e)}, status=403)

    credits, debets = get_credit_history(user_id)

    return render(request, "event/credit.html", {"credits": credits, "debets": debets})


@login_required(login_url="/login")
def success_credit_view(request):
    """Stripe success redirect pro nákup kreditu — ověří platbu a označí transakci.

    Používá select_for_update() + atomic() pro prevenci dvojího přičtení kreditu.
    Webhook (stripe_credit_webhook) je primární cesta — tato view je záloha.
    """
    session_id = request.GET.get("session_id", "")
    if session_id:
        try:
            finalize_credit_transaction_by_session_id(session_id, user=request.user)
            audit_logger.info(
                "credit_checkout_finalized user_id=%s session_id=%s",
                request.user.id,
                session_id,
            )
        except Exception as error:
            logger.error(f"Chyba při potvrzení kreditní platby {session_id}: {error}")
            audit_logger.exception(
                "credit_checkout_finalize_failed user_id=%s session_id=%s",
                request.user.id,
                session_id,
            )
    else:
        finalize_pending_credit_transactions(request.user)
        audit_logger.info(
            "credit_checkout_finalize_pending user_id=%s",
            request.user.id,
        )
    return redirect("event:success-credit-update")


@login_required(login_url="/login")
def success_credit_update_view(request):
    """Potvrzovací stránka po úspěšném nákupu kreditu."""
    messages.success(request, "Váš kredit byl úspěšně navýšen.")
    return render(request, "event/success_credit.html", {})


@login_required(login_url="/login")
@staff_member_required
def recalculate_balances_view(request):
    """Admin stránka — přepočítá kredity a zobrazí výsledek kontroly."""
    context = build_recalculate_balances_context()

    try:
        recalculate_all_balances()
        context["message"] = "Stavy kreditů byly úspěšně překontrolovány."
        context["detail"] = "Přepočet proběhl bez chyby a nové zůstatky jsou uložené."
    except Exception as e:
        logger.error(f"Chyba při přepočtu zůstatků: {e}")
        context["status"] = "error"
        context["message"] = "Při kontrole kreditů došlo k chybě."
        context["detail"] = str(e)

    return render(request, "event/recalculate_balances.html", context)
