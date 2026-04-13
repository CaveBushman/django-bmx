from collections import defaultdict

from django.core.management.base import BaseCommand

from accounts.models import Account, normalize_account_email


class Command(BaseCommand):
    help = "Vypíše účty, které kolidují na e-mailu při case-insensitive porovnání."

    def handle(self, *args, **options):
        grouped_accounts = defaultdict(list)

        for account in Account.objects.order_by("email", "id").only("id", "email", "username"):
            grouped_accounts[normalize_account_email(account.email)].append(account)

        duplicate_groups = [
            (normalized_email, accounts)
            for normalized_email, accounts in grouped_accounts.items()
            if normalized_email and len(accounts) > 1
        ]

        if not duplicate_groups:
            self.stdout.write(self.style.SUCCESS("Nenalezeny žádné case-insensitive duplicitní e-maily."))
            return

        self.stdout.write(self.style.WARNING(f"Nalezeno duplicitních skupin: {len(duplicate_groups)}"))
        for normalized_email, accounts in duplicate_groups:
            account_labels = ", ".join(
                f"id={account.id} email={account.email} username={account.username}"
                for account in accounts
            )
            self.stdout.write(f"{normalized_email}: {account_labels}")
