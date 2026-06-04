import logging
from django.db.models import Sum
from django.apps import apps

logger = logging.getLogger(__name__)


def _sum_amount(queryset, *, alias):
    return queryset.aggregate(**{alias: Sum("amount")})[alias] or 0


def _build_balance_components(*, user_id=None):
    credit_model = apps.get_model("event", "CreditTransaction")
    debit_model = apps.get_model("event", "DebetTransaction")
    rider_stats_charge_model = apps.get_model("rider", "RiderStatsCharge")
    trainer_charge_model = apps.get_model("rider", "TrainerClubCharge")
    mobile_charge_model = apps.get_model("rider", "MobileAppCharge")

    credit_qs = credit_model.objects.filter(payment_complete=True)
    debit_qs = debit_model.objects.filter(payment_valid=True)
    rider_stats_qs = rider_stats_charge_model.objects.filter(payment_valid=True)
    trainer_charge_qs = trainer_charge_model.objects.filter(payment_valid=True)
    mobile_charge_qs = mobile_charge_model.objects.filter(payment_valid=True)

    if user_id is not None:
        credit_qs = credit_qs.filter(user_id=user_id)
        debit_qs = debit_qs.filter(user_id=user_id)
        rider_stats_qs = rider_stats_qs.filter(user_id=user_id)
        trainer_charge_qs = trainer_charge_qs.filter(user_id=user_id)
        mobile_charge_qs = mobile_charge_qs.filter(user_id=user_id)

    return {
        "credit": _sum_amount(credit_qs, alias="total_credit"),
        "event_debit": _sum_amount(debit_qs, alias="total_debit"),
        "rider_stats_debit": _sum_amount(rider_stats_qs, alias="total_rider_stats_debit"),
        "trainer_charge_debit": _sum_amount(trainer_charge_qs, alias="total_trainer_charge_debit"),
        "mobile_app_debit": _sum_amount(mobile_charge_qs, alias="total_mobile_app_debit"),
    }


def _calculate_balance(*, user_id=None):
    components = _build_balance_components(user_id=user_id)
    return (
        components["credit"]
        - components["event_debit"]
        - components["rider_stats_debit"]
        - components["trainer_charge_debit"]
        - components["mobile_app_debit"]
    )


def calculate_account_balance(user_id):
    """Spočítá zůstatek konkrétního uživatele."""
    return _calculate_balance(user_id=user_id)


def calculate_system_balance():
    """Spočítá globální kredit systému ze stejné logiky jako uživatelský kredit."""
    return _calculate_balance()


def get_system_balance_components():
    """Vrátí rozpad globálního kreditu systému po jednotlivých složkách."""
    components = _build_balance_components()
    components["net_balance"] = calculate_system_balance()
    return components


def calculate_user_balance(user_id):
    """Zpětně kompatibilní alias pro výpočet zůstatku uživatele."""
    return calculate_account_balance(user_id)

def recalculate_all_balances():
    """Hromadně přepočítá zůstatky pro všechny aktivní uživatele."""
    Account = apps.get_model("accounts", "Account")

    for user in Account.objects.filter(is_active=True).iterator():
        new_balance = calculate_user_balance(user.id)

        if user.credit != new_balance:
            old_balance = user.credit
            user.credit = new_balance
            user.save(update_fields=["credit"])
            logger.info(
                "Změna kreditu pro %s (%s): %s → %s Kč",
                user.id,
                user.username,
                old_balance,
                new_balance,
            )
