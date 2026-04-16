from django.conf import settings
from django.db import transaction

import stripe

from event.views.entry_helpers import (
    build_checkout_line_items,
    build_foreign_checkout_line_items,
    create_checkout_entries,
    save_foreign_entries,
)


def create_entry_checkout_session(*, event, riders_beginner, riders_20, riders_24):
    line_items = build_checkout_line_items(event, riders_beginner, riders_20, riders_24)
    checkout_session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=line_items,
        mode="payment",
        success_url=settings.YOUR_DOMAIN + f"/event/success/{event.id}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=settings.YOUR_DOMAIN + "/event/cancel?source=entries",
    )

    with transaction.atomic():
        create_checkout_entries(event, checkout_session, riders_beginner, is_beginner=True)
        create_checkout_entries(event, checkout_session, riders_20, is_20=True)
        create_checkout_entries(event, checkout_session, riders_24, is_24=True)

    return checkout_session


def create_foreign_entry_checkout_session(*, event, summary_rows, customer_email):
    line_items = build_foreign_checkout_line_items(event, summary_rows)
    checkout_session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=line_items,
        mode="payment",
        customer_email=customer_email,
        success_url=settings.YOUR_DOMAIN + f"/event/entry-foreign-success/{event.id}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=settings.YOUR_DOMAIN + f"/event/cancel?source=foreign&event_id={event.id}",
    )
    save_foreign_entries(event, checkout_session, summary_rows, customer_email)
    return checkout_session
