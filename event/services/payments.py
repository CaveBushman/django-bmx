from datetime import timedelta

from django.utils import timezone

from event.models import Entry

CHECKOUT_SESSION_KEYS = ("sum_fee", "event", "riders_20", "riders_24")


def get_recent_pending_entries(*, event_id=None):
    """Vrati nedokoncene registrace vytvorene za poslednich 24 hodin."""
    queryset = Entry.objects.filter(
        transaction_date__gte=timezone.now() - timedelta(days=1),
        payment_complete=False,
    )
    if event_id is not None:
        queryset = queryset.filter(event_id=event_id)
    return queryset


def get_entry_amount(entry):
    """Vrati castku konkretni registrace bez ohledu na aktivni kategorii."""
    return (entry.fee_beginner or 0) + (entry.fee_20 or 0) + (entry.fee_24 or 0)


def get_entry_class_name(entry):
    """Vrati nazev aktivni kategorie pro zobrazeni v sablonach."""
    if entry.is_beginner:
        return entry.class_beginner
    if entry.is_20:
        return entry.class_20
    return entry.class_24


def mark_entry_paid(entry, checkout_session):
    """Promitne do Entry uspesnou Stripe platbu."""
    if checkout_session.get("payment_status") != "paid":
        return False

    customer_details = checkout_session.get("customer_details") or {}
    entry.payment_complete = True
    entry.customer_name = customer_details.get("name", "")
    entry.customer_email = customer_details.get("email", "")
    entry.save(update_fields=["payment_complete", "customer_name", "customer_email"])
    return True


def clear_checkout_session(request):
    for key in CHECKOUT_SESSION_KEYS:
        request.session.pop(key, None)


def remove_conflicting_cart_entries(orders):
    """Smaze konflikty v kosiku a vrati smazane polozky.

    Konflikt je:
    - duplicita v aktualnim kosiku uzivatele
    - existujici registrace stejneho jezdce/zavodu/kategorie mimo aktualni kosik
    """
    order_list = list(orders)
    cart_ids = [order.id for order in order_list]
    seen_keys = set()
    duplicates = []

    for order in order_list:
        order_key = (order.event_id, order.rider_id, order.is_beginner, order.is_20, order.is_24)
        has_external_conflict = (
            Entry.objects.filter(
                event_id=order.event_id,
                rider_id=order.rider_id,
                is_beginner=order.is_beginner,
                is_20=order.is_20,
                is_24=order.is_24,
            )
            .exclude(pk__in=cart_ids)
            .exists()
        )

        if order_key in seen_keys or has_external_conflict:
            duplicates.append(order)
            order.delete()
            continue

        seen_keys.add(order_key)

    return duplicates


def enrich_cart_entries(orders):
    """Doplni zobrazovaci data pro kosik a vrati celkovou cenu."""
    total_price = 0
    for order in orders:
        total_price += get_entry_amount(order)
        order.event_class = get_entry_class_name(order)
    return total_price
