from django.core.management.base import BaseCommand

from rider.subscriptions import renew_due_trainer_club_subscriptions


class Command(BaseCommand):
    help = "Obnoví expirovaná trenérská předplatná klubů, pokud mají uživatelé dost kreditu."

    def handle(self, *args, **options):
        result = renew_due_trainer_club_subscriptions()
        self.stdout.write(
            self.style.SUCCESS(
                "Zpracováno: {processed}, obnoveno: {renewed}, expirováno: {expired}, selhalo: {failed}".format(
                    **result
                )
            )
        )
