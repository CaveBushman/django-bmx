from django.core.management.base import BaseCommand

from eshop.models import StockReservation


class Command(BaseCommand):
    help = "Smaže expirované rezervace skladu v e-shopu."

    def handle(self, *args, **options):
        deleted_count = StockReservation.cleanup_expired()
        self.stdout.write(
            self.style.SUCCESS(f"Smazáno expirovaných rezervací: {deleted_count}")
        )
