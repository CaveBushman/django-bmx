"""Najde přihlášky, za které byl kredit stržen víckrát (víc platných debetů).

Jen čte — nic neopravuje. Přeplatek je potřeba prověřit a vrátit ručně
(zneplatnit nadbytečný DebetTransaction v adminu, což zapíše audit).
Dokud duplicity existují, nejde přidat unikátní constraint na
DebetTransaction.entry.
"""

import csv
import sys

from django.core.management.base import BaseCommand
from django.db.models import Count, Sum

from event.models import DebetTransaction


class Command(BaseCommand):
    help = "Vypíše přihlášky s více platnými debetními transakcemi (dvojí stržení kreditu)."

    def add_arguments(self, parser):
        parser.add_argument("--csv", action="store_true", help="Výstup jako CSV (pro účetní/tabulku).")

    def handle(self, *args, **options):
        duplicates = (
            DebetTransaction.objects.filter(entry__isnull=False, payment_valid=True)
            .values("entry_id")
            .annotate(count=Count("id"), total=Sum("amount"))
            .filter(count__gt=1)
            .order_by("entry_id")
        )
        rows = []
        for item in duplicates:
            debets = list(
                DebetTransaction.objects.filter(entry_id=item["entry_id"], payment_valid=True)
                .select_related("user", "entry__event", "entry__rider")
                .order_by("transaction_date", "id")
            )
            first = debets[0]
            entry = first.entry
            fee = (entry.fee_beginner or 0) + (entry.fee_20 or 0) + (entry.fee_24 or 0)
            rows.append({
                "entry_id": item["entry_id"],
                "user_id": first.user_id or "",
                "email": first.user.email if first.user else "",
                "event": entry.event.name if entry.event else "",
                "event_date": entry.event.date.isoformat() if entry.event and entry.event.date else "",
                "rider": str(entry.rider) if entry.rider else "",
                "fee": fee,
                "charged": item["total"],
                "overcharge": item["total"] - fee,
                "debet_ids": " ".join(str(debet.pk) for debet in debets),
                "dates": " | ".join(
                    debet.transaction_date.strftime("%Y-%m-%d %H:%M") if debet.transaction_date else "-"
                    for debet in debets
                ),
            })

        if options["csv"]:
            fields = list(rows[0]) if rows else ["entry_id"]
            writer = csv.DictWriter(sys.stdout, fieldnames=fields, delimiter=";")
            writer.writeheader()
            writer.writerows(rows)
            return

        if not rows:
            self.stdout.write(self.style.SUCCESS("Žádná přihláška nemá víc platných debetů."))
            return

        for row in rows:
            self.stdout.write(
                f"Přihláška #{row['entry_id']}: {row['rider']} – {row['event']} ({row['event_date']}), "
                f"uživatel {row['user_id']} {row['email']}: startovné {row['fee']} Kč, strženo {row['charged']} Kč "
                f"(přeplatek {row['overcharge']} Kč), debety {row['debet_ids']} [{row['dates']}]"
            )
        total = sum(row["overcharge"] for row in rows)
        self.stdout.write(self.style.WARNING(
            f"Celkem {len(rows)} přihlášek, přeplatek {total} Kč. Nadbytečné debety zneplatni v adminu."
        ))
