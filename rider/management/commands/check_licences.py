from django.core.management.base import BaseCommand

from rider.rider import refresh_valid_licences


class Command(BaseCommand):
    help = "Zkontroluje platnost licencí aktivních jezdců a aktualizuje jejich stav."

    def handle(self, *args, **options):
        result = refresh_valid_licences()
        self.stdout.write(
            self.style.SUCCESS(
                "Zkontrolováno: {checked}, platných: {valid}, neplatných: {invalid}, "
                "selhalo: {failed}, ručně potvrzených: {fixed}".format(**result)
            )
        )
