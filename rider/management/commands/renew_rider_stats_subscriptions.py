from django.core.management.base import BaseCommand

from rider.subscriptions import renew_due_rider_stats_subscriptions


class Command(BaseCommand):
    help = "Obnoví expirovaná předplatná prémiových statistik jezdců, pokud mají uživatelé dost kreditu."

    def handle(self, *args, **options):
        result = renew_due_rider_stats_subscriptions()
        self.stdout.write(
            self.style.SUCCESS(
                "Zpracováno: {processed}, obnoveno: {renewed}, expirováno: {expired}, selhalo: {failed}".format(
                    **result
                )
            )
        )
