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

def czech_cup_avg(year):
    """Průměrný počet jezdců na závodech Českého poháru."""
    raise NotImplementedError("Výpočet průměru Českého poháru zatím není implementovaný.")


def czech_league_avg(year):
    """Průměrný počet jezdců na závodech České ligy."""
    raise NotImplementedError("Výpočet průměru České ligy zatím není implementovaný.")


def moravian_league_avg(year):
    """Průměrný počet jezdců na závodech Moravské ligy."""
    raise NotImplementedError("Výpočet průměru Moravské ligy zatím není implementovaný.")
