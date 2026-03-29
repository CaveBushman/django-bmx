"""
finance/func.py — finanční pomocné funkce

Obsah:
  1. Výpočet zůstatku a poplatků (Stripe, celkový kredit)
  2. Statistiky závodu (průměrné počty jezdců) — TODO
"""

from django.db.models import Sum
from django.apps import apps

# Lazy načtení modelů (vyhnutí se circular importům)
CREDIT_MODEL = apps.get_model("event", "CreditTransaction")
DEBIT_MODEL = apps.get_model("event", "DebetTransaction")
STRIPE_MODEL = apps.get_model('event', "StripeFee")
RIDER_STATS_CHARGE_MODEL = apps.get_model("rider", "RiderStatsCharge")
TRAINER_CHARGE_MODEL = apps.get_model("rider", "TrainerClubCharge")


# ===========================================================================
# 1. VÝPOČET ZŮSTATKU
# ===========================================================================

def calculate_user_balance():
    """Vrátí celkový zůstatek na účtu svazu.

    Zůstatek = součet dokončených kreditů − české registrace − prémiové odečty.
    - CreditTransaction.payment_complete=True → přijatá platba
    - DebetTransaction.payment_valid=True → odečet za české registrace
    - RiderStatsCharge.payment_valid=True → odečet za individuální premium
    - TrainerClubCharge.payment_valid=True → odečet za trenérské premium
    """
    credit_sum = CREDIT_MODEL.objects.filter(payment_complete=True).aggregate(total=Sum("amount"))["total"] or 0
    debit_sum = DEBIT_MODEL.objects.filter(payment_valid=True).aggregate(total=Sum("amount"))["total"] or 0
    rider_stats_sum = (
        RIDER_STATS_CHARGE_MODEL.objects.filter(payment_valid=True).aggregate(total=Sum("amount"))["total"] or 0
    )
    trainer_charge_sum = (
        TRAINER_CHARGE_MODEL.objects.filter(payment_valid=True).aggregate(total=Sum("amount"))["total"] or 0
    )

    return credit_sum - debit_sum - rider_stats_sum - trainer_charge_sum


def calculate_stripe_fee(year):
    """Vrátí celkové Stripe poplatky za daný rok."""
    return STRIPE_MODEL.objects.filter(date__year=year).aggregate(total=Sum("fee"))["total"] or 0


# ===========================================================================
# 2. STATISTIKY ZÁVODŮ — TODO
# ===========================================================================

def czech_cup_avg(year):
    """Průměrný počet jezdců na závodech Českého poháru — TODO."""
    pass


def czech_league_avg(year):
    """Průměrný počet jezdců na závodech České ligy — TODO."""
    pass


def moravian_league_avg(year):
    """Průměrný počet jezdců na závodech Moravské ligy — TODO."""
    pass
