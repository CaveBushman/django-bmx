from django.core.management.base import BaseCommand

from event.models import CreditTransaction, Entry
from event.services.checkout_refunds import get_checkout_refund_amount


class Command(BaseCommand):
    help = "Vypíše nekonzistence mezi Entry.checkout a checkout refund kreditními transakcemi."

    def handle(self, *args, **options):
        issues_found = 0

        entries = Entry.objects.select_related("event", "rider", "user").prefetch_related(
            "credit_transactions"
        )
        for entry in entries:
            refunds = [
                refund
                for refund in entry.credit_transactions.all()
                if refund.kind == CreditTransaction.Kind.CHECKOUT_REFUND
            ]
            expected_amount = get_checkout_refund_amount(entry)
            should_have_refund = bool(
                entry.checkout and entry.payment_complete and entry.user_id and expected_amount > 0
            )

            if entry.checkout and not refunds:
                issues_found += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"ENTRY {entry.pk}: checkout=True bez refund transakce"
                    )
                )

            if len(refunds) > 1:
                issues_found += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"ENTRY {entry.pk}: více checkout refund transakcí ({len(refunds)})"
                    )
                )

            for refund in refunds:
                if not should_have_refund:
                    issues_found += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"ENTRY {entry.pk}: refund {refund.pk} existuje, ale stav entry ho nevyžaduje"
                        )
                    )
                if refund.amount != expected_amount:
                    issues_found += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"ENTRY {entry.pk}: refund {refund.pk} má částku {refund.amount}, očekáváno {expected_amount}"
                        )
                    )

        orphan_refunds = CreditTransaction.objects.filter(
            kind=CreditTransaction.Kind.CHECKOUT_REFUND,
            source_entry__isnull=True,
        )
        for refund in orphan_refunds:
            issues_found += 1
            self.stdout.write(
                self.style.WARNING(
                    f"REFUND {refund.pk}: orphan refund bez source_entry"
                )
            )

        if issues_found:
            self.stdout.write(self.style.WARNING(f"Nalezeno problémů: {issues_found}"))
        else:
            self.stdout.write(self.style.SUCCESS("Nenalezeny žádné nekonzistence checkout refundů."))
