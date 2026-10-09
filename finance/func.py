from django.db.models import Sum
from django.apps import apps
from event.credit import calculate_system_balance

STRIPE_MODEL = apps.get_model('event', "StripeFee")


def calculate_user_balance():
    """Kompatibilní wrapper pro globální kredit systému."""
    return calculate_system_balance()


def calculate_system_balance_total():
    """Explicitní název pro globální kredit systému."""
    return calculate_system_balance()


def calculate_stripe_fee(year):
    """Vrátí celkové Stripe poplatky za daný rok."""
    return STRIPE_MODEL.objects.filter(date__year=year).aggregate(total=Sum("fee"))["total"] or 0

