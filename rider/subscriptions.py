from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from accounts.models import Account
from event.credit import calculate_user_balance
from event.models import SeasonSettings
from rider.models import RiderStatsCharge, RiderStatsSubscription


SUBSCRIPTION_PERIOD = timedelta(days=30)


def get_current_season_settings(at_time=None):
    current_time = at_time or timezone.now()
    return SeasonSettings.objects.filter(year=current_time.year).first()


def get_active_rider_stats_subscription(user, rider, at_time=None):
    if not getattr(user, "is_authenticated", False):
        return None

    current_time = at_time or timezone.now()
    return (
        RiderStatsSubscription.objects.filter(
            user=user,
            rider=rider,
            status=RiderStatsSubscription.STATUS_ACTIVE,
            expires_at__gt=current_time,
        )
        .select_related("season", "rider", "user")
        .first()
    )


def has_active_rider_stats_access(user, rider, at_time=None):
    if not getattr(user, "is_authenticated", False):
        return False

    return get_active_rider_stats_subscription(user, rider, at_time=at_time) is not None


def _ensure_rider_is_subscribable(rider):
    if not rider.is_active or not rider.is_approved:
        raise ValueError("Prémiové statistiky lze předplatit jen u aktivního a schváleného jezdce.")


def _get_price_for_current_season(at_time=None):
    season = get_current_season_settings(at_time=at_time)
    if season is None:
        raise ValueError("Pro aktuální rok není nastavená sezona.")
    if season.rider_stats_monthly_price < 0:
        raise ValueError("Cena prémiových statistik v sezoně není platná.")
    return season, season.rider_stats_monthly_price


def _charge_subscription(user, rider, season, subscription, amount, period_start, period_end, reason):
    RiderStatsCharge.objects.create(
        user=user,
        rider=rider,
        season=season,
        subscription=subscription,
        amount=amount,
        period_start=period_start,
        period_end=period_end,
        reason=reason,
    )


def purchase_rider_stats_subscription(user, rider, *, at_time=None):
    current_time = at_time or timezone.now()
    _ensure_rider_is_subscribable(rider)
    season, price = _get_price_for_current_season(at_time=current_time)

    with transaction.atomic():
        account = Account.objects.select_for_update().get(pk=user.pk)
        active_subscription = get_active_rider_stats_subscription(account, rider, at_time=current_time)
        if active_subscription is not None:
            return active_subscription, False

        current_balance = calculate_user_balance(account.pk)
        if price > current_balance:
            raise ValueError("Nedostatek kreditu pro aktivaci prémiových statistik.")

        subscription = (
            RiderStatsSubscription.objects.select_for_update()
            .filter(user=account, rider=rider)
            .order_by("-expires_at", "-id")
            .first()
        )

        period_start = current_time
        period_end = current_time + SUBSCRIPTION_PERIOD

        if subscription is None:
            subscription = RiderStatsSubscription.objects.create(
                user=account,
                rider=rider,
                season=season,
                starts_at=period_start,
                expires_at=period_end,
                status=RiderStatsSubscription.STATUS_ACTIVE,
                monthly_price=price,
                auto_renew=True,
                last_renewed_at=period_start,
            )
        else:
            subscription.season = season
            subscription.starts_at = period_start
            subscription.expires_at = period_end
            subscription.status = RiderStatsSubscription.STATUS_ACTIVE
            subscription.monthly_price = price
            subscription.auto_renew = True
            subscription.last_renewed_at = period_start
            subscription.canceled_at = None
            subscription.save()

        if price > 0:
            _charge_subscription(
                account,
                rider,
                season,
                subscription,
                price,
                period_start,
                period_end,
                RiderStatsCharge.REASON_INITIAL,
            )

        account.credit = calculate_user_balance(account.pk)
        account.save(update_fields=["credit"])
        return subscription, True


def cancel_rider_stats_subscription(subscription, *, at_time=None):
    current_time = at_time or timezone.now()
    subscription.auto_renew = False
    subscription.canceled_at = current_time
    if subscription.expires_at <= current_time:
        subscription.status = RiderStatsSubscription.STATUS_CANCELED
        subscription.save(update_fields=["status", "auto_renew", "canceled_at", "updated"])
    else:
        subscription.save(update_fields=["auto_renew", "canceled_at", "updated"])
    return subscription


def resume_rider_stats_subscription(subscription, *, at_time=None):
    current_time = at_time or timezone.now()
    subscription.auto_renew = True
    subscription.canceled_at = None
    if subscription.expires_at > current_time:
        subscription.status = RiderStatsSubscription.STATUS_ACTIVE
        subscription.save(update_fields=["status", "auto_renew", "canceled_at", "updated"])
    else:
        subscription.save(update_fields=["auto_renew", "canceled_at", "updated"])
    return subscription


def renew_due_rider_stats_subscriptions(*, at_time=None):
    current_time = at_time or timezone.now()
    renewed = 0
    expired = 0
    failed = 0

    due_ids = list(
        RiderStatsSubscription.objects.filter(
            status__in=[RiderStatsSubscription.STATUS_ACTIVE, RiderStatsSubscription.STATUS_PAST_DUE],
            auto_renew=True,
            expires_at__lte=current_time,
        ).values_list("id", flat=True)
    )

    for subscription_id in due_ids:
        with transaction.atomic():
            subscription = (
                RiderStatsSubscription.objects.select_for_update()
                .select_related("user", "rider", "season")
                .filter(id=subscription_id)
                .first()
            )
            if subscription is None:
                continue

            if subscription.status == RiderStatsSubscription.STATUS_CANCELED:
                continue

            if not subscription.rider.is_active or not subscription.rider.is_approved:
                subscription.status = RiderStatsSubscription.STATUS_EXPIRED
                subscription.auto_renew = False
                subscription.save(update_fields=["status", "auto_renew", "updated"])
                expired += 1
                continue

            account = Account.objects.select_for_update().get(pk=subscription.user_id)
            season, price = _get_price_for_current_season(at_time=current_time)
            current_balance = calculate_user_balance(account.pk)
            if price > current_balance:
                subscription.status = RiderStatsSubscription.STATUS_PAST_DUE
                subscription.save(update_fields=["status", "updated"])
                failed += 1
                continue

            period_start = max(subscription.expires_at, current_time)
            period_end = period_start + SUBSCRIPTION_PERIOD
            subscription.season = season
            subscription.starts_at = period_start
            subscription.expires_at = period_end
            subscription.status = RiderStatsSubscription.STATUS_ACTIVE
            subscription.monthly_price = price
            subscription.last_renewed_at = current_time
            subscription.save()

            if price > 0:
                _charge_subscription(
                    account,
                    subscription.rider,
                    season,
                    subscription,
                    price,
                    period_start,
                    period_end,
                    RiderStatsCharge.REASON_RENEWAL,
                )

            account.credit = calculate_user_balance(account.pk)
            account.save(update_fields=["credit"])
            renewed += 1

    return {
        "renewed": renewed,
        "expired": expired,
        "failed": failed,
        "processed": len(due_ids),
    }
