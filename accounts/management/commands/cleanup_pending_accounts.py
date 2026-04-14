from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Account, AccountActivationAuditLog


class Command(BaseCommand):
    help = "Odstraní staré neaktivní účty čekající na aktivaci."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=settings.ACCOUNT_PENDING_ACTIVATION_MAX_AGE_DAYS,
            help="Stáří účtu ve dnech, od kterého se má považovat za expirovaný.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Jen vypíše, co by se smazalo.",
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options["days"])
        queryset = Account.objects.filter(is_active=False, is_staff=False, is_superuser=False, date_joined__lt=cutoff)
        count = queryset.count()

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(f"Dry run: ke smazání je {count} neaktivních účtů."))
            for user in queryset.order_by("date_joined")[:50]:
                self.stdout.write(f"- {user.email} ({user.date_joined:%Y-%m-%d %H:%M})")
            return

        deleted = 0
        for user in queryset.iterator():
            AccountActivationAuditLog.objects.create(
                account=user,
                action=AccountActivationAuditLog.Action.CLEANED_UP,
                source="cleanup_command",
                email_snapshot=user.email,
                note=f"Account older than {options['days']} days removed by cleanup_pending_accounts.",
            )
            user.delete()
            deleted += 1

        self.stdout.write(self.style.SUCCESS(f"Smazáno {deleted} neaktivních účtů čekajících na aktivaci."))
