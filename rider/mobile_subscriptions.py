from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from accounts.models import Account
from event.credit import calculate_user_balance
from event.models import SeasonSettings
from rider.models import MobileAppCharge, MobileAppSubscription, PromoCode, PromoCodeUsage
from rider.subscriptions import cancel_subscription, resume_subscription


SUBSCRIPTION_PERIOD = timedelta(days=365)


def get_current_season_settings(at_time=None):
    current_time = at_time or timezone.now()
    return SeasonSettings.objects.filter(year=current_time.year).first()


def get_active_mobile_app_subscription(user, at_time=None):
    if not getattr(user, "is_authenticated", False):
        return None

    current_time = at_time or timezone.now()
    return (
        MobileAppSubscription.objects.filter(
            user=user,
            status=MobileAppSubscription.STATUS_ACTIVE,
            expires_at__gt=current_time,
        )
        .select_related("season", "user")
        .first()
    )


def has_active_mobile_app_access(user, at_time=None):
    if not getattr(user, "is_authenticated", False):
        return False
    return get_active_mobile_app_subscription(user, at_time=at_time) is not None


def _get_mobile_price_for_current_season(at_time=None):
    season = get_current_season_settings(at_time=at_time)
    if season is None:
        raise ValueError("Pro aktuální rok není nastavená sezona.")
    if season.mobile_app_annual_price < 0:
        raise ValueError("Cena předplatného mobilní aplikace v sezoně není platná.")
    return season, season.mobile_app_annual_price


def _record_charge(user, season, subscription, amount, period_start, period_end, reason):
    charge = MobileAppCharge.objects.create(
        user=user,
        season=season,
        subscription=subscription,
        amount=amount,
        period_start=period_start,
        period_end=period_end,
        reason=reason,
    )
    from finance.subscription_invoices import SubscriptionInvoiceService

    SubscriptionInvoiceService().generate_for_mobile_charge(charge)


def purchase_mobile_app_subscription(user, *, promo_code_str=None, at_time=None):
    current_time = at_time or timezone.now()
    season, price = _get_mobile_price_for_current_season(at_time=current_time)

    promo = None
    discount = 0
    if promo_code_str:
        promo = _validate_promo_code(promo_code_str, PromoCode.PRODUCT_MOBILE_APP, user, at_time=current_time)
        discount = promo.calculate_discount(price)

    effective_price = max(0, price - discount)

    with transaction.atomic():
        account = Account.objects.select_for_update().get(pk=user.pk)
        active_subscription = get_active_mobile_app_subscription(account, at_time=current_time)
        if active_subscription is not None:
            return active_subscription, False

        current_balance = calculate_user_balance(account.pk)
        if effective_price > current_balance:
            raise ValueError("Nedostatek kreditu pro aktivaci předplatného mobilní aplikace.")

        subscription = (
            MobileAppSubscription.objects.select_for_update()
            .filter(user=account)
            .order_by("-expires_at", "-id")
            .first()
        )

        period_start = current_time
        period_end = current_time + SUBSCRIPTION_PERIOD

        if subscription is None:
            subscription = MobileAppSubscription.objects.create(
                user=account,
                season=season,
                starts_at=period_start,
                expires_at=period_end,
                status=MobileAppSubscription.STATUS_ACTIVE,
                monthly_price=price,
                auto_renew=True,
                last_renewed_at=period_start,
            )
        else:
            subscription.season = season
            subscription.starts_at = period_start
            subscription.expires_at = period_end
            subscription.status = MobileAppSubscription.STATUS_ACTIVE
            subscription.monthly_price = price
            subscription.auto_renew = True
            subscription.last_renewed_at = period_start
            subscription.canceled_at = None
            subscription.save()

        reason = MobileAppCharge.REASON_PROMO if promo else MobileAppCharge.REASON_INITIAL
        if effective_price > 0:
            _record_charge(account, season, subscription, effective_price, period_start, period_end, reason)

        if promo:
            _consume_promo_code(promo, account, PromoCode.PRODUCT_MOBILE_APP, discount)

        account.credit = calculate_user_balance(account.pk)
        account.save(update_fields=["credit"])
        return subscription, True


def _validate_promo_code(code_str, product, user, at_time=None):
    current_time = at_time or timezone.now()
    try:
        promo = PromoCode.objects.select_for_update().get(code=code_str.strip().upper())
    except PromoCode.DoesNotExist:
        raise ValueError("Promo kód neexistuje.")

    if not promo.is_valid(at_time=current_time):
        raise ValueError("Promo kód není platný nebo byl již vyčerpán.")

    if promo.product not in (product, PromoCode.PRODUCT_ALL):
        raise ValueError("Promo kód nelze použít pro tento produkt.")

    if PromoCodeUsage.objects.filter(promo_code=promo, user=user).exists():
        raise ValueError("Tento promo kód jste již použili.")

    return promo


def _consume_promo_code(promo, user, product, discount_applied):
    PromoCodeUsage.objects.create(
        promo_code=promo,
        user=user,
        product=product,
        discount_applied=discount_applied,
    )
    PromoCode.objects.filter(pk=promo.pk).update(used_count=promo.used_count + 1)


def cancel_mobile_app_subscription(subscription, *, at_time=None):
    return cancel_subscription(subscription, at_time=at_time)


def resume_mobile_app_subscription(subscription, *, at_time=None):
    return resume_subscription(subscription, at_time=at_time)


def renew_due_mobile_app_subscriptions(*, at_time=None):
    current_time = at_time or timezone.now()
    renewed = 0
    expired = 0
    failed = 0

    due_ids = list(
        MobileAppSubscription.objects.filter(
            status__in=[MobileAppSubscription.STATUS_ACTIVE, MobileAppSubscription.STATUS_PAST_DUE],
            auto_renew=True,
            expires_at__lte=current_time,
        ).values_list("id", flat=True)
    )

    for subscription_id in due_ids:
        with transaction.atomic():
            subscription = (
                MobileAppSubscription.objects.select_for_update()
                .select_related("user", "season")
                .filter(id=subscription_id)
                .first()
            )
            if subscription is None or subscription.status == MobileAppSubscription.STATUS_CANCELED:
                continue

            account = Account.objects.select_for_update().get(pk=subscription.user_id)
            season, price = _get_mobile_price_for_current_season(at_time=current_time)
            current_balance = calculate_user_balance(account.pk)
            if price > current_balance:
                subscription.status = MobileAppSubscription.STATUS_PAST_DUE
                subscription.save(update_fields=["status", "updated"])
                failed += 1
                continue

            period_start = max(subscription.expires_at, current_time)
            period_end = period_start + SUBSCRIPTION_PERIOD
            subscription.season = season
            subscription.starts_at = period_start
            subscription.expires_at = period_end
            subscription.status = MobileAppSubscription.STATUS_ACTIVE
            subscription.monthly_price = price
            subscription.last_renewed_at = current_time
            subscription.save()

            if price > 0:
                _record_charge(
                    account, season, subscription, price, period_start, period_end, MobileAppCharge.REASON_RENEWAL
                )

            account.credit = calculate_user_balance(account.pk)
            account.save(update_fields=["credit"])
            renewed += 1

    return {"renewed": renewed, "expired": expired, "failed": failed, "processed": len(due_ids)}
