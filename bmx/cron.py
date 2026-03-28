from rider.rider import refresh_valid_licences
from rider.subscriptions import renew_due_rider_stats_subscriptions, renew_due_trainer_club_subscriptions


def valid_licence_scheduled():
    """Spustí pravidelnou kontrolu platnosti licencí."""
    return refresh_valid_licences()


def renew_rider_stats_subscriptions_scheduled():
    """Obnoví expirovaná předplatná prémiových statistik jezdců."""
    return renew_due_rider_stats_subscriptions()


def renew_trainer_club_subscriptions_scheduled():
    """Obnoví expirovaná trenérská klubová předplatná."""
    return renew_due_trainer_club_subscriptions()
