"""Platby e-shopu kartou přes Stripe Checkout.

Průběh objednávky:

1. Checkout vytvoří ``Order`` (stav PENDING), odečte sklad a založí Stripe
   Checkout session s omezenou platností (``PAYMENT_WINDOW``).
2. Zaplacení potvrdí kterákoli ze tří cest — návrat zákazníka ze Stripe
   (``finalize_checkout_session``), webhook ``checkout.session.completed``
   (``handle_stripe_event``) nebo cron dohledání (``resolve_stale_orders``).
   ``Order.mark_paid`` je idempotentní, takže pořadí nevadí.
3. Nezaplacená session vyprší → objednávka se stornuje a sklad se vrátí.
4. Storno zaplacené objednávky nejdřív vrátí peníze ve Stripe (s
   idempotency klíčem) a teprve pak změní objednávku v databázi.

Session e-shopu se poznají podle metadat ``eshop_order_id``.
"""

import logging
from datetime import timedelta
from decimal import Decimal

import stripe
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from .models import Order, OrderHistory

logger = logging.getLogger(__name__)

#: Jak dlouho drží objednávka zboží, než ji zákazník zaplatí. Stripe vyžaduje
#: platnost session aspoň 30 minut.
PAYMENT_WINDOW = timedelta(minutes=35)

#: Metadata, podle kterých webhook pozná session e-shopu.
METADATA_KEY = "eshop_order_id"


class PaymentError(Exception):
    """Platební bránu se nepodařilo použít; zpráva je určená zákazníkovi."""


def _stripe_key():
    stripe.api_key = settings.STRIPE_SECRET_KEY


def _to_minor_units(amount):
    return int((Decimal(amount) * 100).quantize(Decimal("1")))


def _from_minor_units(amount):
    if amount is None:
        return None
    return (Decimal(amount) / 100).quantize(Decimal("0.01"))


def _order_url(order, query=""):
    path = reverse("eshop:order-confirmation", args=[order.pk])
    return f"{settings.YOUR_DOMAIN}{path}{query}"


def _line_items(order):
    line_items = []
    for item in order.items.select_related("variant__product"):
        variant = item.variant
        name = variant.product.name if variant else "Produkt"
        if variant and variant.label:
            name = f"{name} — {variant.label}"
        line_items.append({
            "price_data": {
                "currency": "czk",
                "unit_amount": _to_minor_units(item.unit_price),
                "product_data": {"name": name},
            },
            "quantity": item.quantity,
        })
    return line_items


def create_checkout_session(order):
    """Založí Stripe Checkout session pro objednávku a uloží ji k objednávce."""
    _stripe_key()
    expires_at = timezone.now() + PAYMENT_WINDOW
    metadata = {METADATA_KEY: str(order.pk)}
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=_line_items(order),
            customer_email=order.email or None,
            client_reference_id=f"eshop-{order.pk}",
            metadata=metadata,
            payment_intent_data={
                "metadata": metadata,
                "description": f"E-shop objednávka #{order.pk}",
            },
            expires_at=int(expires_at.timestamp()),
            success_url=_order_url(order, "?session_id={CHECKOUT_SESSION_ID}"),
            cancel_url=_order_url(order, "?payment=canceled"),
            idempotency_key=f"eshop-order-{order.pk}-checkout",
        )
    except stripe.StripeError as exc:
        logger.exception("Stripe Checkout session pro e-shop objednávku %s se nepodařilo založit.", order.pk)
        raise PaymentError("Platební bránu se nepodařilo otevřít. Zkus to prosím za chvíli znovu.") from exc

    Order.objects.filter(pk=order.pk).update(
        stripe_session_id=session["id"],
        payment_expires_at=expires_at,
        updated=timezone.now(),
    )
    order.stripe_session_id = session["id"]
    order.payment_expires_at = expires_at
    OrderHistory.record(
        order=order,
        action=OrderHistory.Action.PAYMENT_STARTED,
        note=f"Stripe Checkout {session['id']}",
    )
    return session


def _apply_session(order, session, *, actor=None):
    """Promítne stav Stripe session do objednávky. Vrací True, je-li zaplacená."""
    if session.get("payment_status") != "paid":
        return False
    changed = order.mark_paid(
        session_id=session["id"],
        payment_intent=session.get("payment_intent") or "",
        amount_paid=_from_minor_units(session.get("amount_total")),
        actor=actor,
    )
    if changed:
        expected = _to_minor_units(order.total)
        if session.get("amount_total") is not None and session["amount_total"] != expected:
            logger.error(
                "E-shop objednávka %s: Stripe zaplaceno %s haléřů, objednávka stojí %s haléřů.",
                order.pk, session["amount_total"], expected,
            )
    order.refresh_from_db()
    if order.status == Order.Status.CANCELED and order.paid_at and not order.refunded_at:
        _refund_late_payment(order)
    return True


def finalize_checkout_session(order, session_id, *, actor=None):
    """Ověří session po návratu zákazníka ze Stripe a potvrdí platbu."""
    if not session_id or session_id != order.stripe_session_id:
        return False
    _stripe_key()
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.StripeError:
        logger.exception("Nepodařilo se ověřit Stripe session %s (objednávka %s).", session_id, order.pk)
        return False
    return _apply_session(order, session, actor=actor)


def get_open_checkout_url(order):
    """Vrátí URL rozpracované platby, nebo None, pokud už platit nejde."""
    if not order.is_awaiting_payment or not order.stripe_session_id:
        return None
    _stripe_key()
    try:
        session = stripe.checkout.Session.retrieve(order.stripe_session_id)
    except stripe.StripeError:
        logger.exception("Nepodařilo se načíst Stripe session objednávky %s.", order.pk)
        return None
    if _apply_session(order, session):
        return None
    if session.get("status") == "open":
        return session.get("url")
    if session.get("status") == "expired":
        _cancel_expired(order)
    return None


def _cancel_expired(order):
    try:
        order.cancel_by_user(note="Platba nebyla dokončena včas, objednávka zrušena a zboží vráceno na sklad.")
    except ValueError:
        # Mezitím už zaplacená nebo zrušená — nic dalšího není potřeba.
        pass


def _refund_late_payment(order):
    _stripe_key()
    try:
        refund = stripe.Refund.create(
            payment_intent=order.stripe_payment_intent,
            idempotency_key=f"eshop-refund-{order.pk}",
        )
    except stripe.StripeError:
        logger.exception("Automatické vrácení platby po stornu objednávky %s selhalo.", order.pk)
        return
    Order.objects.filter(pk=order.pk).update(
        refunded_at=timezone.now(), stripe_refund_id=refund["id"], updated=timezone.now(),
    )
    OrderHistory.record(
        order=order,
        action=OrderHistory.Action.REFUNDED,
        note=f"Platba přijatá po stornu vrácena na kartu ({refund['id']}).",
    )


def cancel_order(order, *, actor=None):
    """Stornuje objednávku včetně vrácení platby nebo uzavření platební brány."""
    order.refresh_from_db()
    if not order.is_cancelable:
        raise ValueError("Tuto objednávku už nelze stornovat, protože byla předána nebo už je zrušená.")

    _stripe_key()
    if order.is_awaiting_payment and order.stripe_session_id:
        # Zavřít platební bránu, aby zákazník nemohl zaplatit stornovanou objednávku.
        try:
            stripe.checkout.Session.expire(order.stripe_session_id)
        except stripe.StripeError:
            session = None
            try:
                session = stripe.checkout.Session.retrieve(order.stripe_session_id)
            except stripe.StripeError:
                logger.exception("Stripe session objednávky %s nejde ověřit.", order.pk)
            if session is not None and _apply_session(order, session, actor=actor):
                order.refresh_from_db()
            # Pokud session nejde ověřit, storno pokračuje; pozdní platbu
            # zachytí webhook a automaticky ji vrátí.

    refund_id = ""
    if order.paid_at and not order.refunded_at and order.payment_method == Order.PaymentMethod.STRIPE:
        try:
            refund = stripe.Refund.create(
                payment_intent=order.stripe_payment_intent,
                idempotency_key=f"eshop-refund-{order.pk}",
            )
        except stripe.StripeError as exc:
            logger.exception("Vrácení platby za objednávku %s selhalo.", order.pk)
            raise ValueError(
                "Platbu se nepodařilo vrátit na kartu. Objednávka zůstává platná, kontaktuj nás prosím."
            ) from exc
        refund_id = refund["id"]

    order.cancel_by_user(actor=actor, stripe_refund_id=refund_id)


def handle_stripe_event(stripe_event):
    """Zpracuje webhook pro session e-shopu. Vrací False, pokud session není naše."""
    session = stripe_event["data"]["object"]
    metadata = session.get("metadata") or {}
    order_id = metadata.get(METADATA_KEY)
    if not order_id:
        return False

    order = Order.objects.filter(pk=order_id, stripe_session_id=session.get("id")).first()
    if order is None:
        logger.warning("Webhook pro neznámou e-shop objednávku %s (session %s).", order_id, session.get("id"))
        return True

    event_type = stripe_event["type"]
    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        _apply_session(order, session)
    elif event_type == "checkout.session.expired" and order.is_awaiting_payment:
        _cancel_expired(order)
    return True


def resolve_stale_orders(*, now=None):
    """Dohledá objednávky, jejichž platba už měla skončit (pojistka za webhook)."""
    now = now or timezone.now()
    stale = Order.objects.filter(
        status=Order.Status.PENDING,
        payment_method=Order.PaymentMethod.STRIPE,
        paid_at__isnull=True,
        payment_expires_at__lt=now - timedelta(minutes=5),
    )
    _stripe_key()
    resolved = {"paid": 0, "canceled": 0, "errors": 0}
    for order in stale:
        try:
            session = stripe.checkout.Session.retrieve(order.stripe_session_id) if order.stripe_session_id else None
        except stripe.StripeError:
            logger.exception("Nepodařilo se ověřit Stripe session objednávky %s.", order.pk)
            resolved["errors"] += 1
            continue
        if session is not None and _apply_session(order, session):
            resolved["paid"] += 1
        elif session is None or session.get("status") != "open":
            _cancel_expired(order)
            resolved["canceled"] += 1
    return resolved
