from django.core.management.base import BaseCommand
from django.db import transaction

from rider.models import ForeignRider, Rider


class Command(BaseCommand):
    help = "Překlopí historická startovní čísla z integer pole `plate` do textového pole `plate_text`."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Pouze vypíše, kolik záznamů by se změnilo, bez zápisu do databáze.",
        )

    @staticmethod
    def _copy_plate_values(model, dry_run=False):
        records = list(
            model.objects.filter(plate__isnull=False, plate__gt=0).order_by("pk")
        )
        to_update = []
        copied = 0
        skipped = 0

        for record in records:
            current_value = (record.plate_text or "").strip()
            expected_value = str(record.plate)
            if current_value:
                skipped += 1
                continue

            record.plate_text = expected_value
            to_update.append(record)
            copied += 1

        if to_update and not dry_run:
            model.objects.bulk_update(to_update, ["plate_text"])

        return copied, skipped

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        with transaction.atomic():
            rider_copied, rider_skipped = self._copy_plate_values(Rider, dry_run=dry_run)
            foreign_copied, foreign_skipped = self._copy_plate_values(ForeignRider, dry_run=dry_run)

            if dry_run:
                transaction.set_rollback(True)

        verb = "Bylo by překlopeno" if dry_run else "Překlopeno"
        self.stdout.write(
            self.style.SUCCESS(
                (
                    f"{verb}: Rider {rider_copied}, přeskočeno {rider_skipped}; "
                    f"ForeignRider {foreign_copied}, přeskočeno {foreign_skipped}."
                )
            )
        )
