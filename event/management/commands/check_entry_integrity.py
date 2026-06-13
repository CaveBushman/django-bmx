"""Detekce osiřelých referencí na jezdce.

`Entry.rider` a `Result.rider` mají `db_constraint=False`, takže databáze
nehlídá referenční integritu. Příkaz najde záznamy odkazující na
neexistujícího jezdce, zaloguje je a u Entry je volitelně (`--fix`) vynuluje.

Pozor na rozdíl mezi oběma vazbami:

* `Entry.rider` odkazuje na celočíselný PK jezdce. Osiřelý Entry je skutečný
  viselec — jezdec byl smazán a registrace zůstala. `--fix` ho vynuluje
  (stejně jako on_delete=SET_NULL).

* `Result.rider` odkazuje na `uci_id` (to_field). Osiřelý Result obvykle NENÍ
  chyba: jde o zahraničního nebo neregistrovaného jezdce, jehož výsledek byl
  naimportován, ale jako Rider nikdy nevznikl (viz CLAUDE.md). Hodnota uci_id
  je smysluplná a může se propojit, až jezdec vznikne. Proto Result jen
  reportujeme a `--fix` ho NEVYNULUJE — to by zničilo historickou vazbu.
"""

import logging

from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef

from event.models import Entry, Result
from rider.models import Rider

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Najde Entry/Result záznamy odkazující na neexistujícího jezdce "
        "(db_constraint=False). S --fix vynuluje pouze osiřelé Entry."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Vynuluje rider u osiřelých Entry (Result se nikdy nevynuluje).",
        )
        parser.add_argument(
            "--sample",
            type=int,
            default=10,
            help="Kolik ID osiřelých záznamů vypsat. Výchozí 10.",
        )

    def handle(self, *args, **options):
        fix = options["fix"]
        sample = options["sample"]

        # Entry.rider → Rider.pk (osiřelý = skutečný viselec po smazaném jezdci)
        orphan_entries = Entry.objects.filter(rider_id__isnull=False).exclude(
            Exists(Rider.objects.filter(pk=OuterRef("rider_id")))
        )
        # Result.rider → Rider.uci_id (osiřelý = obvykle zahraniční/neregistrovaný jezdec)
        orphan_results = Result.objects.filter(rider_id__isnull=False).exclude(
            Exists(Rider.objects.filter(uci_id=OuterRef("rider_id")))
        )

        total = 0

        entry_count = orphan_entries.count()
        total += entry_count
        if entry_count:
            ids = list(orphan_entries.values_list("id", flat=True)[:sample])
            msg = f"Entry: {entry_count} osiřelých záznamů (ukázka ID: {ids})"
            logger.warning("Integrity check – %s", msg)
            self.stdout.write(self.style.WARNING(msg))
            if fix:
                updated = orphan_entries.update(rider_id=None)
                logger.warning("Integrity check – Entry: vynulováno %d záznamů", updated)
                self.stdout.write(self.style.SUCCESS(f"Entry: vynulováno {updated} záznamů"))
        else:
            self.stdout.write(self.style.SUCCESS("Entry: žádné osiřelé záznamy"))

        result_count = orphan_results.count()
        total += result_count
        if result_count:
            ids = list(orphan_results.values_list("id", flat=True)[:sample])
            msg = (
                f"Result: {result_count} osiřelých záznamů (ukázka ID: {ids}) "
                f"— pravděpodobně zahraniční/neregistrovaní jezdci, NEVYNULOVÁNO"
            )
            logger.warning("Integrity check – %s", msg)
            self.stdout.write(self.style.WARNING(msg))
        else:
            self.stdout.write(self.style.SUCCESS("Result: žádné osiřelé záznamy"))

        if total == 0:
            self.stdout.write(self.style.SUCCESS("Referenční integrita OK."))
        elif entry_count and not fix:
            self.stdout.write(
                self.style.NOTICE("Osiřelé Entry lze vynulovat spuštěním s --fix.")
            )
