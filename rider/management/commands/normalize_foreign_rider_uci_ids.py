from django.core.management.base import BaseCommand
from rider.models import ForeignRider
from event.utils import normalize_uci_id


class Command(BaseCommand):
    help = "Normalizuje UCI ID zahraničních jezdců (odstraní písmena, ponechá jen číslice)"

    def handle(self, *args, **options):
        updated = 0
        for rider in ForeignRider.objects.all():
            normalized = normalize_uci_id(rider.uci_id)
            if rider.uci_id != normalized:
                rider.uci_id = normalized
                ForeignRider.objects.filter(pk=rider.pk).update(uci_id=normalized)
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Normalizováno {updated} UCI ID"))
