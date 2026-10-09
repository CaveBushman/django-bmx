from django.core.management.base import BaseCommand

from eshop.payments import resolve_stale_orders


class Command(BaseCommand):
    help = (
        "Dohledá e-shop objednávky, jejichž platba kartou už měla skončit: "
        "zaplacené potvrdí, nezaplacené zruší a vrátí zboží na sklad."
    )

    def handle(self, *args, **options):
        result = resolve_stale_orders()
        self.stdout.write(self.style.SUCCESS(
            f"Zaplaceno: {result['paid']}, zrušeno: {result['canceled']}, chyby: {result['errors']}"
        ))
