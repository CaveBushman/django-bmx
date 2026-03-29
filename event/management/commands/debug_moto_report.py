from django.core.management.base import BaseCommand

from event.models import Entry, EntryForeign, Event, RaceRun
from finance.models import EventCashReceipt


class Command(BaseCommand):
    help = "Debug moto kontrola – zobrazí data plateb vs MOTO jezdce pro daný závod"

    def add_arguments(self, parser):
        parser.add_argument("event_id", type=int)

    def handle(self, *args, **options):
        event_id = options["event_id"]
        try:
            event = Event.objects.get(pk=event_id)
        except Event.DoesNotExist:
            self.stderr.write(f"Závod {event_id} neexistuje.")
            return

        self.stdout.write(f"\n=== Závod: {event.name} (ID {event.id}) ===\n")

        # --- Zaplacené online registrace ---
        entries = list(
            Entry.objects.filter(event=event, payment_complete=True).select_related("rider")
        )
        self.stdout.write(f"Entry (payment_complete=True): {len(entries)}")
        no_rider = sum(1 for e in entries if e.rider is None)
        no_uci = sum(1 for e in entries if e.rider and not e.rider.uci_id)
        ok = sum(1 for e in entries if e.rider and e.rider.uci_id)
        self.stdout.write(f"  → s UCI ID: {ok}")
        self.stdout.write(f"  → rider=None: {no_rider}")
        self.stdout.write(f"  → rider existuje, ale uci_id=0/None: {no_uci}")

        paid_uci_ids = set()
        for e in entries:
            if e.rider and e.rider.uci_id:
                paid_uci_ids.add(str(e.rider.uci_id).strip())

        # --- Zahraniční registrace ---
        foreign = list(EntryForeign.objects.filter(event=event, payment_complete=True))
        self.stdout.write(f"\nEntryForeign (payment_complete=True): {len(foreign)}")
        for f in foreign:
            uci = str(f.uci_id).strip().upper() if f.uci_id else ""
            if uci:
                paid_uci_ids.add(uci)

        # --- Hotovostní doklady ---
        receipts = list(EventCashReceipt.objects.filter(event=event))
        self.stdout.write(f"\nEventCashReceipt: {len(receipts)}")
        receipt_no_uci = sum(1 for r in receipts if not r.uci_id)
        self.stdout.write(f"  → bez UCI ID: {receipt_no_uci}")
        for r in receipts:
            uci = str(r.uci_id).strip().upper() if r.uci_id else ""
            if uci:
                paid_uci_ids.add(uci)

        self.stdout.write(f"\nCelkem unikátních zaplacených UCI ID: {len(paid_uci_ids)}")

        # --- MOTO jezdci ---
        runs = (
            RaceRun.objects.filter(event=event, round_type="MOTO")
            .select_related("rider", "result")
        )
        moto_uci = {}
        for run in runs:
            uci = ""
            name = ""
            if run.rider and run.rider.uci_id:
                uci = str(run.rider.uci_id).strip()
                name = f"{run.rider.first_name} {run.rider.last_name}"
            elif run.result and run.result.rider_id:
                uci = str(run.result.rider_id).strip()
                name = f"{run.result.first_name} {run.result.last_name}"
            if uci and uci not in moto_uci:
                moto_uci[uci] = (name, run.category or "")

        self.stdout.write(f"Unikátní MOTO jezdci s UCI ID: {len(moto_uci)}")

        # --- Porovnání ---
        unpaid = {uci: info for uci, info in moto_uci.items() if uci not in paid_uci_ids}
        self.stdout.write(f"\nJezdci v MOTO bez záznamu platby: {len(unpaid)}")
        for uci, (name, cat) in sorted(unpaid.items(), key=lambda x: x[1][0]):
            self.stdout.write(f"  UCI {uci}  {name}  [{cat}]")
