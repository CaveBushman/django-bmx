"""
Logika pro uplatňování promo kódů s kreditem.

Kódy typu DISCOUNT_CREDIT neposkytují slevu na předplatné —
místo toho připíší fixní částku kreditu na účet uživatele.
"""
from django.db import transaction
from django.utils import timezone

from accounts.models import Account
from event.credit import calculate_user_balance
from event.models import CreditTransaction
from rider.models import PromoCode, PromoCodeUsage


def redeem_credit_promo_code(user, code_str: str, *, at_time=None):
    """
    Uplatní promo kód s kreditem. Přidá definovanou částku na účet uživatele.

    Vrátí (amount, True) při úspěchu. Vyvolá ValueError při neplatném kódu.
    """
    current_time = at_time or timezone.now()

    with transaction.atomic():
        account = Account.objects.select_for_update().get(pk=user.pk)

        promo = _get_valid_credit_promo(code_str, account, current_time)
        amount = promo.discount_value

        CreditTransaction.objects.create(
            user=account,
            amount=amount,
            transaction_id=f"promo-{promo.code}-{account.pk}-{int(current_time.timestamp())}",
            payment_complete=True,
            kind=CreditTransaction.Kind.PROMO,
        )

        PromoCodeUsage.objects.create(
            promo_code=promo,
            user=account,
            product=PromoCode.PRODUCT_CREDIT,
            discount_applied=amount,
        )
        PromoCode.objects.filter(pk=promo.pk).update(used_count=promo.used_count + 1)

        account.credit = calculate_user_balance(account.pk)
        account.save(update_fields=["credit"])

    return amount, True


def _get_valid_credit_promo(code_str, user, at_time):
    try:
        promo = PromoCode.objects.select_for_update().get(code=code_str.strip().upper())
    except PromoCode.DoesNotExist:
        raise ValueError("Promo kód neexistuje.")

    if promo.discount_type != PromoCode.DISCOUNT_CREDIT:
        raise ValueError("Tento promo kód nelze uplatnit jako kredit.")

    if not promo.is_valid(at_time=at_time):
        raise ValueError("Promo kód není platný nebo byl již vyčerpán.")

    if PromoCodeUsage.objects.filter(promo_code=promo, user=user).exists():
        raise ValueError("Tento promo kód jste již použili.")

    return promo
