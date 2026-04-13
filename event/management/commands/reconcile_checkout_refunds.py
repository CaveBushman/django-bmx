from django.core.management.base import BaseCommand

from event.models import CreditTransaction, Entry
from event.services.checkout_refunds import (
    get_checkout_refund_amount,
    get_checkout_refund_credit,
    sync_checkout_refund_credit,
)


class Command(BaseCommand):
    help = "Zkontroluje a případně opraví refund kreditů pro registrace s checkout."

    def add_arguments(self, parser):
        parser.add_argument("--entry-id", type=int, help="Zpracovat jen konkrétní registraci.")
        parser.add_argument("--dry-run", action="store_true", help="Pouze vypíše rozdíly bez zápisu.")
        parser.add_argument(
            "--delete-orphans",
            action="store_true",
            help="Smazat refund kreditní transakce, které nejsou navázané na žádnou registraci.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        delete_orphans = options["delete_orphans"]
        entry_id = options.get("entry_id")

        entries = Entry.objects.select_related("user", "event", "rider").order_by("id")
        if entry_id:
            entries = entries.filter(pk=entry_id)

        checked = 0
        changed = 0

        for entry in entries:
            checked += 1
            refund = get_checkout_refund_credit(entry)
            should_have_refund = bool(
                entry.checkout
                and entry.payment_complete
                and entry.user_id
                and get_checkout_refund_amount(entry) > 0
            )

            mismatch = False
            if should_have_refund and refund is None:
                mismatch = True
            elif not should_have_refund and refund is not None:
                mismatch = True
            elif should_have_refund and refund is not None:
                mismatch = any(
                    (
                        refund.user_id != entry.user_id,
                        refund.amount != get_checkout_refund_amount(entry),
                        refund.payment_complete is not True,
                        refund.kind != CreditTransaction.Kind.CHECKOUT_REFUND,
                        refund.source_entry_id != entry.id,
                    )
                )

            if not mismatch:
                continue

            changed += 1
            self.stdout.write(
                f"Entry {entry.pk}: refund mismatch detected (checkout={entry.checkout}, payment_complete={entry.payment_complete})"
            )
            if not dry_run:
                sync_checkout_refund_credit(entry)

        orphan_qs = CreditTransaction.objects.filter(
            kind=CreditTransaction.Kind.CHECKOUT_REFUND,
            source_entry__isnull=True,
        )
        orphan_count = orphan_qs.count()
        if orphan_count:
            self.stdout.write(f"Found {orphan_count} orphan checkout refund credit transactions.")
            if delete_orphans and not dry_run:
                orphan_qs.delete()
                self.stdout.write("Orphan checkout refund transactions deleted.")

        summary = (
            f"Checked {checked} entries, found {changed} mismatches"
            f"{' (dry-run)' if dry_run else ''}."
        )
        self.stdout.write(self.style.SUCCESS(summary))
