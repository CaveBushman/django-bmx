"""Logika prémiových předplatných jezdců a trenér-klub (Stripe, obnovy, fakturace)."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from accounts.models import Account
from event.credit import calculate_user_balance
from event.models import SeasonSettings
from rider.models import (
    RiderStatsCharge,
    RiderStatsSubscription,
    TrainerClubCharge,
    TrainerClubSubscription,
)


SUBSCRIPTION_PERIOD = timedelta(days=30)

_STATUS_CANCELED = "canceled"
_STATUS_ACTIVE = "active"


# ---------------------------------------------------------------------------
# Generické cancel / resume — fungují s jakýmkoliv subscription modelem
# ---------------------------------------------------------------------------

def cancel_subscription(subscription, *, at_time=None):
    """Vypne auto-obnovu. Pokud již vypršelo, nastaví stav canceled."""
    current_time = at_time or timezone.now()
    subscription.auto_renew = False
    subscription.canceled_at = current_time
    if subscription.expires_at <= current_time:
        subscription.status = _STATUS_CANCELED
        subscription.save(update_fields=["status", "auto_renew", "canceled_at", "updated"])
    else:
        subscription.save(update_fields=["auto_renew", "canceled_at", "updated"])
    return subscription


def resume_subscription(subscription, *, at_time=None):
    """Zapne auto-obnovu. Pokud ještě platí, nastaví stav active."""
    current_time = at_time or timezone.now()
    subscription.auto_renew = True
    subscription.canceled_at = None
    if subscription.expires_at > current_time:
        subscription.status = _STATUS_ACTIVE
        subscription.save(update_fields=["status", "auto_renew", "canceled_at", "updated"])
    else:
        subscription.save(update_fields=["auto_renew", "canceled_at", "updated"])
    return subscription


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


def _get_trainer_price_for_current_season(product, *, at_time=None):
    season = get_current_season_settings(at_time=at_time)
    if season is None:
        raise ValueError("Pro aktuální rok není nastavená sezona.")

    if product == TrainerClubSubscription.PRODUCT_CLUB_STATS:
        price = season.trainer_club_stats_monthly_price
    elif product == TrainerClubSubscription.PRODUCT_EXTENDED:
        price = season.trainer_extended_monthly_price
    else:
        raise ValueError("Neplatný typ trenérského předplatného.")

    if price < 0:
        raise ValueError("Cena trenérského předplatného v sezoně není platná.")
    return season, price


def _charge_subscription(user, rider, season, subscription, amount, period_start, period_end, reason):
    charge = RiderStatsCharge.objects.create(
        user=user,
        rider=rider,
        season=season,
        subscription=subscription,
        amount=amount,
        period_start=period_start,
        period_end=period_end,
        reason=reason,
    )
    from finance.subscription_invoices import SubscriptionInvoiceService

    SubscriptionInvoiceService().generate_for_rider_charge(charge)


def _charge_trainer_subscription(user, club, season, subscription, product, amount, period_start, period_end, reason):
    charge = TrainerClubCharge.objects.create(
        user=user,
        club=club,
        season=season,
        subscription=subscription,
        product=product,
        amount=amount,
        period_start=period_start,
        period_end=period_end,
        reason=reason,
    )
    from finance.subscription_invoices import SubscriptionInvoiceService

    SubscriptionInvoiceService().generate_for_trainer_charge(charge)


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
    return cancel_subscription(subscription, at_time=at_time)


def resume_rider_stats_subscription(subscription, *, at_time=None):
    return resume_subscription(subscription, at_time=at_time)


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


def get_active_trainer_club_subscription(user, club, product, at_time=None):
    if not getattr(user, "is_authenticated", False):
        return None

    current_time = at_time or timezone.now()
    return (
        TrainerClubSubscription.objects.filter(
            user=user,
            club=club,
            product=product,
            status=TrainerClubSubscription.STATUS_ACTIVE,
            expires_at__gt=current_time,
        )
        .select_related("season", "club", "user")
        .first()
    )


def _get_raw_active_trainer_extended_subscription(user, at_time=None):
    if not getattr(user, "is_authenticated", False):
        return None

    current_time = at_time or timezone.now()
    return (
        TrainerClubSubscription.objects.filter(
            user=user,
            product=TrainerClubSubscription.PRODUCT_EXTENDED,
            status=TrainerClubSubscription.STATUS_ACTIVE,
            expires_at__gt=current_time,
        )
        .select_related("season", "club", "user")
        .order_by("-expires_at", "-id")
        .first()
    )


def get_active_trainer_extended_subscription(user, at_time=None):
    current_time = at_time or timezone.now()
    _deactivate_extended_if_no_stats_access(user, at_time=current_time)
    return _get_raw_active_trainer_extended_subscription(user, at_time=current_time)


def _deactivate_extended_if_no_stats_access(user, *, at_time=None):
    current_time = at_time or timezone.now()
    extended_subscription = _get_raw_active_trainer_extended_subscription(user, at_time=current_time)
    if extended_subscription is None:
        return None

    has_any_active_stats = TrainerClubSubscription.objects.filter(
        user=user,
        product=TrainerClubSubscription.PRODUCT_CLUB_STATS,
        status=TrainerClubSubscription.STATUS_ACTIVE,
        expires_at__gt=current_time,
    ).exists()
    if has_any_active_stats:
        return extended_subscription

    extended_subscription.status = TrainerClubSubscription.STATUS_EXPIRED
    extended_subscription.auto_renew = False
    extended_subscription.canceled_at = current_time
    extended_subscription.save(update_fields=["status", "auto_renew", "canceled_at", "updated"])
    return extended_subscription


def _disable_extended_auto_renew_if_no_stats_auto_renew(user, *, at_time=None):
    current_time = at_time or timezone.now()
    extended_subscription = _get_raw_active_trainer_extended_subscription(user, at_time=current_time)
    if extended_subscription is None:
        return None

    has_any_renewable_stats = TrainerClubSubscription.objects.filter(
        user=user,
        product=TrainerClubSubscription.PRODUCT_CLUB_STATS,
        status=TrainerClubSubscription.STATUS_ACTIVE,
        expires_at__gt=current_time,
        auto_renew=True,
    ).exists()
    if has_any_renewable_stats or not extended_subscription.auto_renew:
        return extended_subscription

    extended_subscription.auto_renew = False
    extended_subscription.canceled_at = current_time
    extended_subscription.save(update_fields=["auto_renew", "canceled_at", "updated"])
    return extended_subscription


def has_active_trainer_club_stats_access(user, club, at_time=None):
    if not getattr(user, "is_authenticated", False):
        return False

    return get_active_trainer_club_subscription(
        user,
        club,
        TrainerClubSubscription.PRODUCT_CLUB_STATS,
        at_time=at_time,
    ) is not None


def has_any_active_trainer_club_stats_access(user, at_time=None):
    if not getattr(user, "is_authenticated", False):
        return False

    current_time = at_time or timezone.now()
    return TrainerClubSubscription.objects.filter(
        user=user,
        product=TrainerClubSubscription.PRODUCT_CLUB_STATS,
        status=TrainerClubSubscription.STATUS_ACTIVE,
        expires_at__gt=current_time,
    ).exists()


def _get_any_active_trainer_stats_subscription(user, at_time=None):
    if not getattr(user, "is_authenticated", False):
        return None

    current_time = at_time or timezone.now()
    return (
        TrainerClubSubscription.objects.filter(
            user=user,
            product=TrainerClubSubscription.PRODUCT_CLUB_STATS,
            status=TrainerClubSubscription.STATUS_ACTIVE,
            expires_at__gt=current_time,
        )
        .select_related("season", "club", "user")
        .order_by("-expires_at", "-id")
        .first()
    )


def has_active_trainer_club_extended_access(user, club, at_time=None):
    if not getattr(user, "is_authenticated", False):
        return False

    return (
        has_active_trainer_club_stats_access(user, club, at_time=at_time)
        and get_active_trainer_extended_subscription(user, at_time=at_time) is not None
    )


def _ensure_trainer_can_subscribe(account, club):
    if not getattr(account, "is_trainer", False):
        raise ValueError("Trenérské předplatné může aktivovat jen uživatel s rolí trenéra.")
    if not account.trainer_clubs.filter(pk=club.pk).exists():
        raise ValueError("Trenérské předplatné lze aktivovat jen pro přiřazený klub.")
    if not club.is_active:
        raise ValueError("Trenérské předplatné lze aktivovat jen pro aktivní klub.")


def purchase_trainer_club_subscription(user, club, product, *, at_time=None):
    current_time = at_time or timezone.now()

    with transaction.atomic():
        account = Account.objects.select_for_update().prefetch_related("trainer_clubs").get(pk=user.pk)
        _ensure_trainer_can_subscribe(account, club)
        season, price = _get_trainer_price_for_current_season(product, at_time=current_time)

        if product == TrainerClubSubscription.PRODUCT_EXTENDED:
            active_subscription = get_active_trainer_extended_subscription(account, at_time=current_time)
        else:
            active_subscription = get_active_trainer_club_subscription(account, club, product, at_time=current_time)
        if active_subscription is not None:
            return active_subscription, False

        if product == TrainerClubSubscription.PRODUCT_EXTENDED and not has_any_active_trainer_club_stats_access(account, at_time=current_time):
            raise ValueError("Rozšířené trenérské předplatné lze aktivovat až po předplacení statistik alespoň jednoho klubu.")

        current_balance = calculate_user_balance(account.pk)
        if price > current_balance:
            raise ValueError("Nedostatek kreditu pro aktivaci trenérského předplatného.")

        subscription_query = TrainerClubSubscription.objects.select_for_update().filter(user=account, product=product)
        if product == TrainerClubSubscription.PRODUCT_CLUB_STATS:
            subscription_query = subscription_query.filter(club=club)
        subscription = subscription_query.order_by("-expires_at", "-id").first()

        period_start = current_time
        period_end = current_time + SUBSCRIPTION_PERIOD

        if subscription is None:
            subscription = TrainerClubSubscription.objects.create(
                user=account,
                club=club,
                season=season,
                product=product,
                starts_at=period_start,
                expires_at=period_end,
                status=TrainerClubSubscription.STATUS_ACTIVE,
                monthly_price=price,
                auto_renew=True,
                last_renewed_at=period_start,
            )
        else:
            subscription.season = season
            subscription.club = club
            subscription.starts_at = period_start
            subscription.expires_at = period_end
            subscription.status = TrainerClubSubscription.STATUS_ACTIVE
            subscription.monthly_price = price
            subscription.auto_renew = True
            subscription.last_renewed_at = period_start
            subscription.canceled_at = None
            subscription.save()

        if price > 0:
            _charge_trainer_subscription(
                account,
                club,
                season,
                subscription,
                product,
                price,
                period_start,
                period_end,
                TrainerClubCharge.REASON_INITIAL,
            )

        account.credit = calculate_user_balance(account.pk)
        account.save(update_fields=["credit"])
        return subscription, True


def cancel_trainer_club_subscription(subscription, *, at_time=None):
    current_time = at_time or timezone.now()
    cancel_subscription(subscription, at_time=current_time)
    if subscription.product == TrainerClubSubscription.PRODUCT_CLUB_STATS:
        _disable_extended_auto_renew_if_no_stats_auto_renew(subscription.user, at_time=current_time)
        _deactivate_extended_if_no_stats_access(subscription.user, at_time=current_time)
    return subscription


def resume_trainer_club_subscription(subscription, *, at_time=None):
    return resume_subscription(subscription, at_time=at_time)


def _expire_trainer_subscription(subscription, *, side_effect=None):
    """Nastaví subscription jako expired a volitelně spustí side effect."""
    subscription.status = TrainerClubSubscription.STATUS_EXPIRED
    subscription.auto_renew = False
    subscription.save(update_fields=["status", "auto_renew", "updated"])
    if side_effect:
        side_effect()


def _check_trainer_eligibility(subscription, account, current_time):
    """
    Ověří, zda je předplatné způsobilé k obnovení.
    Vrátí True pokud ano; False a rovnou expired/upraví subscription pokud ne.
    """
    if not account.is_trainer:
        _expire_trainer_subscription(subscription)
        return False

    if subscription.product == TrainerClubSubscription.PRODUCT_CLUB_STATS:
        if not account.trainer_clubs.filter(pk=subscription.club_id).exists():
            _expire_trainer_subscription(
                subscription,
                side_effect=lambda: _deactivate_extended_if_no_stats_access(account, at_time=current_time),
            )
            return False
    else:
        anchor = _get_any_active_trainer_stats_subscription(account, at_time=current_time)
        if anchor is None:
            _expire_trainer_subscription(subscription)
            return False
        if subscription.club_id != anchor.club_id:
            subscription.club = anchor.club

    return True


def renew_due_trainer_club_subscriptions(*, at_time=None):
    current_time = at_time or timezone.now()
    renewed = 0
    expired = 0
    failed = 0

    due_ids = list(
        TrainerClubSubscription.objects.filter(
            status__in=[TrainerClubSubscription.STATUS_ACTIVE, TrainerClubSubscription.STATUS_PAST_DUE],
            auto_renew=True,
            expires_at__lte=current_time,
        ).values_list("id", flat=True)
    )

    for subscription_id in due_ids:
        with transaction.atomic():
            subscription = (
                TrainerClubSubscription.objects.select_for_update()
                .select_related("user", "club", "season")
                .filter(id=subscription_id)
                .first()
            )
            if subscription is None or subscription.status == TrainerClubSubscription.STATUS_CANCELED:
                continue

            account = Account.objects.select_for_update().prefetch_related("trainer_clubs").get(pk=subscription.user_id)

            if not _check_trainer_eligibility(subscription, account, current_time):
                expired += 1
                continue

            season, price = _get_trainer_price_for_current_season(subscription.product, at_time=current_time)
            if price > calculate_user_balance(account.pk):
                subscription.status = TrainerClubSubscription.STATUS_PAST_DUE
                subscription.save(update_fields=["status", "updated"])
                failed += 1
                continue

            period_start = max(subscription.expires_at, current_time)
            period_end = period_start + SUBSCRIPTION_PERIOD
            subscription.season = season
            subscription.starts_at = period_start
            subscription.expires_at = period_end
            subscription.status = TrainerClubSubscription.STATUS_ACTIVE
            subscription.monthly_price = price
            subscription.last_renewed_at = current_time
            subscription.save()

            if price > 0:
                _charge_trainer_subscription(
                    account, subscription.club, season, subscription,
                    subscription.product, price, period_start, period_end,
                    TrainerClubCharge.REASON_RENEWAL,
                )

            account.credit = calculate_user_balance(account.pk)
            account.save(update_fields=["credit"])
            if subscription.product == TrainerClubSubscription.PRODUCT_CLUB_STATS:
                _deactivate_extended_if_no_stats_access(account, at_time=current_time)
                _disable_extended_auto_renew_if_no_stats_auto_renew(account, at_time=current_time)
            renewed += 1

    return {"renewed": renewed, "expired": expired, "failed": failed, "processed": len(due_ids)}
