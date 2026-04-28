"""
Management command: link_czech_foreign_entries

Projde všechny záznamy EntryForeign bez navázaného rider a zkusí je propojit
s českým jezdcem (Rider) podle UCI ID. Typický případ: Čech se zahraniční licencí
(např. americkou) přihlášený přes formulář zahraničních jezdců.

Použití:
    python manage.py link_czech_foreign_entries
    python manage.py link_czech_foreign_entries --dry-run
    python manage.py link_czech_foreign_entries --all   # přepíše i již propojené
"""

import logging
from django.core.management.base import BaseCommand
from django.db import transaction

from event.models import EntryForeign
from event.utils import normalize_uci_id
from rider.models import Rider

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Propojí záznamy EntryForeign s českými jezdci (Rider) podle UCI ID."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Pouze vypíše co by se změnilo, nic nezapíše do DB.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            dest="relink_all",
            help="Přepíše propojení i u záznamů kde rider již je nastaven.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        relink_all = options["relink_all"]

        qs = EntryForeign.objects.all()
        if not relink_all:
            qs = qs.filter(rider__isnull=True)

        # Načíst všechny české jezdce do mapy pro jediný DB dotaz
        czech_riders = {rider.uci_id: rider for rider in Rider.objects.all()}

        linked = 0
        skipped = 0
        already_linked = 0
        not_found = 0

        for entry in qs.iterator():
            normalized = normalize_uci_id(entry.uci_id)
            if not normalized:
                skipped += 1
                continue

            try:
                uci_id_int = int(normalized)
            except (TypeError, ValueError):
                skipped += 1
                continue

            czech_rider = czech_riders.get(uci_id_int)
            if czech_rider is None:
                not_found += 1
                continue

            if entry.rider_id == czech_rider.pk:
                already_linked += 1
                continue

            self.stdout.write(
                "  EntryForeign pk={} | {} {} (UCI {}) → Rider pk={} ({} {}){}".format(
                    entry.pk,
                    entry.first_name,
                    entry.last_name,
                    uci_id_int,
                    czech_rider.pk,
                    czech_rider.first_name,
                    czech_rider.last_name,
                    " [DRY RUN]" if dry_run else "",
                )
            )

            if not dry_run:
                with transaction.atomic():
                    EntryForeign.objects.filter(pk=entry.pk).update(rider=czech_rider)
            linked += 1

        self.stdout.write(self.style.SUCCESS(
            "\nHotovo: propojeno={}, již propojeno={}, nenalezeno v CZE={}, přeskočeno={}{}".format(
                linked,
                already_linked,
                not_found,
                skipped,
                " [DRY RUN — nic nebylo zapsáno]" if dry_run else "",
            )
        ))
