"""Synchronizace jezdců a klubů s centrální databází Event Control Admin.

Příklady:

    python manage.py sync_event_control                       # kluby + jezdci z API
    python manage.py sync_event_control --entity riders       # jen jezdci
    python manage.py sync_event_control --since 2026-01-01    # přírůstkově od data
    python manage.py sync_event_control --dry-run             # jen report, nic nezapisuje
    python manage.py sync_event_control --entity clubs --file kluby.json

``--file`` čte stejný JSON, jaký vrací centrální API (pole záznamů nebo
``{"results": [...]}``) — hodí se pro jednorázový import i pro test mapování,
než bude centrální API dostupné.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date, parse_datetime

from event.services.event_control_sync import (
    EventControlAdminClient,
    EventControlAdminUnavailable,
    sync_clubs,
    sync_riders,
)

HANDLERS = {"clubs": sync_clubs, "riders": sync_riders}


class Command(BaseCommand):
    help = "Synchronizuje jezdce a kluby s centrální databází Event Control Admin."

    def add_arguments(self, parser):
        parser.add_argument(
            "--entity",
            choices=["all", "clubs", "riders"],
            default="all",
            help="Která entita se má synchronizovat (výchozí: all — kluby, pak jezdci).",
        )
        parser.add_argument("--since", help="Přírůstkově od data/času v ISO formátu.")
        parser.add_argument("--file", help="Načte záznamy z JSON souboru místo z API.")
        parser.add_argument("--dry-run", action="store_true", help="Nic nezapisuje, jen vypíše výsledek.")

    def handle(self, *args, **options):
        entities = ["clubs", "riders"] if options["entity"] == "all" else [options["entity"]]
        dry_run = options["dry_run"]
        since = self._parse_since(options.get("since"))

        if options.get("file"):
            if len(entities) != 1:
                raise CommandError("S --file je potřeba zvolit konkrétní --entity (clubs nebo riders).")
            records = self._load_file(options["file"])
            log = HANDLERS[entities[0]](records, source="command", dry_run=dry_run)
            self._report(log)
            return

        client = EventControlAdminClient()
        if not client.configured:
            raise CommandError(
                "EVENT_CONTROL_ADMIN_URL není nastavené — doplň ho v bmx/.env, nebo použij --file."
            )

        for entity in entities:
            try:
                records = client.fetch(entity, updated_since=since)
            except EventControlAdminUnavailable as error:
                raise CommandError(str(error)) from error
            log = HANDLERS[entity](records, source="command", dry_run=dry_run)
            self._report(log)

    @staticmethod
    def _parse_since(raw):
        if not raw:
            return None
        parsed = parse_datetime(raw) or parse_date(raw)
        if parsed is None:
            raise CommandError("--since musí být v ISO formátu (2026-01-01 nebo 2026-01-01T10:00:00).")
        return parsed

    @staticmethod
    def _load_file(path):
        source = Path(path)
        if not source.exists():
            raise CommandError(f"Soubor {source} neexistuje.")
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise CommandError(f"Soubor {source} se nepodařilo přečíst: {error}") from error
        if isinstance(data, dict):
            data = data.get("results") or data.get("data") or data.get("items") or []
        if not isinstance(data, list):
            raise CommandError("JSON musí být pole záznamů nebo objekt s klíčem results.")
        return data

    def _report(self, log):
        self.stdout.write(
            self.style.SUCCESS(
                f"{log.get_entity_display()}: přijato {log.received}, spárováno {log.matched}, "
                f"založeno {log.created}, konflikty {log.conflicts}, přeskočeno {log.skipped}"
                f"{' (dry-run)' if log.dry_run else ''}"
            )
        )
        conflicts = (log.detail or {}).get("conflicts") or {}
        for key, diffs in list(conflicts.items())[:20]:
            fields = ", ".join(f"{field}: web={values['local']!r} vs centrální={values['remote']!r}" for field, values in diffs.items())
            self.stdout.write(f"  konflikt {key} — {fields}")
        if len(conflicts) > 20:
            self.stdout.write(f"  … a další {len(conflicts) - 20} konfliktů (detail v logu synchronizace)")
