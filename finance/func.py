# finance/credit.py (nebo event/utils.py)
from django.db.models import Sum
from django.apps import apps
from datetime import date

CREDIT_MODEL = apps.get_model("event", "CreditTransaction")
DEBIT_MODEL = apps.get_model("event", "DebetTransaction")
STRIPE_MODEL = apps.get_model('event', "StripeFee")

def calculate_user_balance():
    """
    Vrátí zůstatek uživatele = (součet kreditů) - (součet debetů).
    - only_completed: u kreditů bere jen dokončené platby (payment_complete=True)
    - only_valid: u debetů bere jen platné položky (payment_valid=True)
    """

    credits_qs = CREDIT_MODEL.objects.filter( payment_complete = True)
    debits_qs = DEBIT_MODEL.objects.filter(payment_valid=True)
    stripe_qs = STRIPE_MODEL.objects.all()

    credit_sum = credits_qs.aggregate(total=Sum("amount"))["total"] or 0
    debit_sum  = debits_qs.aggregate(total=Sum("amount"))["total"] or 0
    stripe_sum = stripe_qs.aggregate(total=Sum("fee"))["total"] or 0

    return credit_sum - debit_sum - stripe_sum

def calculate_stripe_fee(year):
    """ calculate Stripe fee in params year"""

    stripe_qs = STRIPE_MODEL.objects.filter(date__year = year)
    stripe_sum = stripe_qs.aggregate(total=Sum("fee"))["total"] or 0

    return stripe_sum


def czech_cup_avg(year):
    """ Function to return avg riders on Czech Cup"""
    pass


def czech_league_avg(year):

    pass


def moravian_league_avg(year):

    pass


