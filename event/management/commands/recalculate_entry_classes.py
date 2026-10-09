"""Přepočítá kategorie přihlášek závodu podle jeho aktuální sady kategorií.

Kategorie se do přihlášky ukládá při registraci (``Entry.class_20`` …) a dál
se nemění. Když pořadatel sadu kategorií závodu (``classes_and_fees_like``)
během přihlašování změní, starší přihlášky si nesou staré názvy — a export
přihlášek (REM, API pro BMX Event Control / BIKODY) je posílá dál, takže je
časomíra nezná (Pardubice 11. 10. 2026: „Boys 7/8", „JM/U23/EM").

Jen pro **nadcházející závod v aktuální sezóně**: kategorie se počítá
z dnešní věkové třídy jezdce (``Rider.class_20``), takže u starších závodů
by přepsala historii podle dnešního věku.

Výchozí běh jen ukáže, co by se změnilo; zapíše až ``--apply``. Startovné se
nemění (je zaplacené). Zahraniční přihlášky se jen nahlásí, když jejich
kategorie v aktuální sadě není — kategorie se u nich počítá z data narození,
ne z profilu jezdce, a oprava patří do ruční kontroly.
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from event.func import resolve_event_classes
from event.models import Entry, EntryForeign, Event

audit_logger = logging.getLogger("audit")

_NE_NAZVY = {"id", "event_name", "created", "updated"}


def _nazvy_sady(entry_classes) -> set[str]:
    """Všechny názvy kategorií v sadě (bez poplatků a metadat)."""
    nazvy = set()
    for field in entry_classes._meta.concrete_fields:
        if field.name in _NE_NAZVY or field.name.endswith("_fee") or field.get_internal_type() != "CharField":
            continue
        hodnota = getattr(entry_classes, field.name)
        if hodnota:
            nazvy.add(hodnota)
    return nazvy


def _nova_kategorie(event, entry):
    """(pole, stará, nová) pro start přihlášky, nebo None, když nejde spočítat."""
    rider = entry.rider
    if rider is None:
        return None
    if entry.is_beginner:
        return "class_beginner", entry.class_beginner, resolve_event_classes(event, rider, is_20=True, is_beginner=True)
    if entry.is_20:
        return "class_20", entry.class_20, resolve_event_classes(event, rider, is_20=True)
    if entry.is_24:
        return "class_24", entry.class_24, resolve_event_classes(event, rider, is_20=False)
    return None


class Command(BaseCommand):
    help = "Přepočítá kategorie zaplacených přihlášek závodu podle jeho aktuální sady kategorií (bez --apply jen náhled)."

    def add_arguments(self, parser):
        parser.add_argument("event_id", type=int)
        parser.add_argument("--apply", action="store_true", help="Změny opravdu zapsat.")

    def handle(self, event_id, apply, **options):
        event = Event.objects.select_related("classes_and_fees_like").filter(pk=event_id).first()
        if event is None:
            raise CommandError(f"Závod {event_id} neexistuje.")
        if not event.classes_and_fees_like_id:
            raise CommandError("Závod nemá nastavenou sadu kategorií (classes_and_fees_like).")
        dnes = timezone.localdate()
        if event.date is None or event.date < dnes or event.date.year != dnes.year:
            raise CommandError(
                "Přepočet jde jen u nadcházejícího závodu v aktuální sezóně — kategorie se počítá "
                "z dnešní věkové třídy jezdce a u starších závodů by přepsala historii."
            )

        nazvy = _nazvy_sady(event.classes_and_fees_like)
        self.stdout.write(f"{event.name} ({event.date}) — sada „{event.classes_and_fees_like.event_name}“")

        zmeny = []
        prihlasky = (
            Entry.objects.filter(event=event, payment_complete=True, checkout=False)
            .select_related("rider")
            .order_by("rider__last_name", "rider__first_name")
        )
        for entry in prihlasky:
            vysledek = _nova_kategorie(event, entry)
            if vysledek is None:
                self.stdout.write(self.style.WARNING(f"  přihláška #{entry.pk}: bez jezdce nebo startu — přeskočeno"))
                continue
            pole, stara, nova = vysledek
            if nova and stara != nova:
                zmeny.append((entry, pole, stara, nova))
                self.stdout.write(f"  {entry.rider} (#{entry.pk}): {stara or '—'} → {nova}")

        for zahranicni in EntryForeign.objects.filter(event=event, payment_complete=True, checkout=False):
            for kategorie in (zahranicni.class_20 if zahranicni.is_20 else None, zahranicni.class_24 if zahranicni.is_24 else None):
                if kategorie and kategorie not in nazvy:
                    self.stdout.write(self.style.WARNING(
                        f"  zahraniční {zahranicni.first_name} {zahranicni.last_name} (#{zahranicni.pk}): "
                        f"kategorie „{kategorie}“ v sadě není — zkontrolujte ručně"
                    ))

        if not zmeny:
            self.stdout.write(self.style.SUCCESS("Všechny přihlášky mají kategorii podle aktuální sady."))
            return
        if not apply:
            self.stdout.write(self.style.WARNING(f"Náhled: {len(zmeny)} přihlášek by se změnilo. Zapíšete s --apply."))
            return

        with transaction.atomic():
            for entry, pole, stara, nova in zmeny:
                # update(): jen přejmenování kategorie — bez signálů platby/checkoutu.
                Entry.objects.filter(pk=entry.pk).update(**{pole: nova})
                audit_logger.info(
                    "entry_class_recalculated entry_id=%s event_id=%s field=%s old=%r new=%r",
                    entry.pk, event.pk, pole, stara, nova,
                )
        self.stdout.write(self.style.SUCCESS(f"Zapsáno: {len(zmeny)} přihlášek."))
