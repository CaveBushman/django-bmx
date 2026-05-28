import logging

import stripe
from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")


def get_foreign_entry_refund_amount(entry):
    """Vrátí celkové startovné v Kč (fee_20 + fee_24)."""
    return (entry.fee_20 or 0) + (entry.fee_24 or 0)


def _get_payment_intent_id(session_id: str) -> str:
    """Načte PaymentIntent ID ze Stripe Checkout Session."""
    stripe.api_key = settings.STRIPE_SECRET_KEY
    session = stripe.checkout.Session.retrieve(session_id)
    payment_intent = session.get("payment_intent") or session.payment_intent
    if not payment_intent:
        raise ValueError(
            f"Stripe Session {session_id} nemá přiřazený PaymentIntent. "
            "Možná šlo o bezplatnou nebo credit-based registraci."
        )
    return payment_intent


def issue_foreign_entry_stripe_refund(entry) -> str:
    """
    Vydá Stripe partial refund za jedno EntryForeign.

    Podmínky:
    - payment_complete=True
    - checkout=True
    - stripe_refund_id je prázdný (refund ještě nebyl vydán)
    - fee > 0
    - transaction_id není prázdný (platba proběhla přes Stripe)

    Vrátí Stripe Refund ID (re_xxx).
    Vyhodí ValueError nebo stripe.error.StripeError při chybě.
    """
    amount_czk = get_foreign_entry_refund_amount(entry)

    if not entry.payment_complete:
        raise ValueError(f"EntryForeign #{entry.pk}: platba není dokončena (payment_complete=False).")
    if not entry.checkout:
        raise ValueError(f"EntryForeign #{entry.pk}: checkout není nastaven.")
    if entry.stripe_refund_id:
        logger.info(
            "foreign_entry_refund_skipped_already_refunded entry_id=%s refund_id=%s",
            entry.pk,
            entry.stripe_refund_id,
        )
        return entry.stripe_refund_id
    if amount_czk <= 0:
        raise ValueError(f"EntryForeign #{entry.pk}: nulové nebo záporné startovné ({amount_czk} Kč), refund nelze vydat.")
    if not entry.transaction_id:
        raise ValueError(f"EntryForeign #{entry.pk}: chybí transaction_id (Stripe Session ID).")

    payment_intent_id = _get_payment_intent_id(entry.transaction_id)

    stripe.api_key = settings.STRIPE_SECRET_KEY
    refund = stripe.Refund.create(
        payment_intent=payment_intent_id,
        amount=amount_czk * 100,  # haléře
        metadata={
            "entry_foreign_id": str(entry.pk),
            "uci_id": entry.uci_id or "",
            "event_id": str(entry.event_id or ""),
        },
    )

    refund_id = refund["id"]

    with transaction.atomic():
        from event.models import EntryForeign
        EntryForeign.objects.filter(pk=entry.pk).update(stripe_refund_id=refund_id)
        entry.stripe_refund_id = refund_id

    audit_logger.info(
        "foreign_entry_stripe_refund_issued entry_id=%s refund_id=%s amount_czk=%s "
        "payment_intent=%s session_id=%s uci_id=%s event_id=%s",
        entry.pk,
        refund_id,
        amount_czk,
        payment_intent_id,
        entry.transaction_id,
        entry.uci_id,
        entry.event_id,
    )

    return refund_id


def capture_foreign_entry_checkout_state(entry):
    """Uloží předchozí stav checkout na instanci (pro detekci přechodu v post_save)."""
    if not entry.pk:
        entry._previous_checkout = False
        return

    from event.models import EntryForeign
    prev = EntryForeign.objects.filter(pk=entry.pk).values("checkout").first()
    entry._previous_checkout = bool(prev["checkout"]) if prev else False


def sync_foreign_entry_stripe_refund(entry):
    """
    Voláno z post_save signalu. Vydá refund pokud checkout přešel False → True.
    Chyby loguje ale nevyhazuje (neblokují uložení záznamu).
    """
    previous_checkout = getattr(entry, "_previous_checkout", None)
    if previous_checkout is None:
        return

    checkout_activated = (not previous_checkout) and bool(entry.checkout)
    if not checkout_activated:
        return

    if entry.stripe_refund_id:
        return

    try:
        refund_id = issue_foreign_entry_stripe_refund(entry)
        logger.info(
            "foreign_entry_refund_auto_issued entry_id=%s refund_id=%s",
            entry.pk,
            refund_id,
        )
    except ValueError as exc:
        logger.warning(
            "foreign_entry_refund_skipped entry_id=%s reason=%s",
            entry.pk,
            exc,
        )
    except stripe.error.StripeError as exc:
        logger.error(
            "foreign_entry_stripe_refund_failed entry_id=%s stripe_error=%s",
            entry.pk,
            exc,
        )
