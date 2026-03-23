import os
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone


DEFAULT_TARGET_DIRS = (
    "api-payloads",
    "event_stats",
    "participation",
    "riders_on_events",
)


class Command(BaseCommand):
    help = "Smaže staré generované pomocné soubory z MEDIA_ROOT."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Smazat soubory starší než zadaný počet dní. Výchozí 30.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Pouze vypíše, co by se smazalo, bez skutečného mazání.",
        )

    def handle(self, *args, **options):
        max_age_days = options["days"]
        dry_run = options["dry_run"]
        cutoff = timezone.now() - timedelta(days=max_age_days)

        deleted_files = 0
        scanned_files = 0

        for relative_dir in DEFAULT_TARGET_DIRS:
            target_dir = os.path.join(settings.MEDIA_ROOT, relative_dir)
            if not os.path.isdir(target_dir):
                continue

            for root, _, files in os.walk(target_dir):
                for filename in files:
                    file_path = os.path.join(root, filename)
                    scanned_files += 1
                    modified_at = timezone.make_aware(
                        timezone.datetime.fromtimestamp(os.path.getmtime(file_path)),
                        timezone.get_current_timezone(),
                    )
                    if modified_at >= cutoff:
                        continue

                    if dry_run:
                        self.stdout.write(f"DRY-RUN delete: {file_path}")
                    else:
                        os.remove(file_path)
                        self.stdout.write(f"Deleted: {file_path}")
                    deleted_files += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Scanned {scanned_files} files, {'would delete' if dry_run else 'deleted'} {deleted_files}."
            )
        )
