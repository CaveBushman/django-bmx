"""
Odešle FCM push notifikace závodníkům přihlášeným na závody konající se za N dní.

Spuštění (např. z cronu den před závodem v 9:00):
    python manage.py send_race_notifications --days 1

Parametry:
    --days  Kolik dní dopředu odesílat (default: 1)
    --dry-run  Jen zobrazí, co by se odeslalo, bez skutečného odeslání
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from event.models_events import Event


class Command(BaseCommand):
    help = 'Odešle FCM push notifikace na závody konající se za N dní.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=1,
            help='Počet dní dopředu (default: 1)',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Pouze zobrazí, co by se odeslalo, bez odeslání',
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        target_date = date.today() + timedelta(days=days)

        events = Event.objects.filter(date=target_date, is_canceled=False)

        if not events.exists():
            self.stdout.write(f'Žádné závody {target_date} (za {days} dní).')
            return

        try:
            import firebase_admin
            from firebase_admin import messaging
            try:
                firebase_admin.get_app()
            except ValueError:
                import os
                from django.conf import settings
                cred_path = getattr(settings, 'FIREBASE_CREDENTIALS_PATH', None)
                if cred_path and os.path.exists(cred_path):
                    cred = firebase_admin.credentials.Certificate(cred_path)
                    firebase_admin.initialize_app(cred)
                else:
                    self.stderr.write('FIREBASE_CREDENTIALS_PATH není nastaven.')
                    return
        except ImportError:
            self.stderr.write('firebase-admin není nainstalován.')
            return

        for event in events:
            topic = f'event_{event.pk}'
            title = 'Závod za dveřmi 🏁'
            body = f'Zítra závodíte: {event.name}'

            self.stdout.write(
                f'{"[DRY-RUN] " if dry_run else ""}Odesílám na topic {topic}: {body}'
            )

            if not dry_run:
                try:
                    message = messaging.Message(
                        notification=messaging.Notification(
                            title=title,
                            body=body,
                        ),
                        data={'path': f'/events/{event.pk}'},
                        topic=topic,
                    )
                    response = messaging.send(message)
                    self.stdout.write(self.style.SUCCESS(
                        f'  ✓ Odesláno: {response}'
                    ))
                except Exception as e:
                    self.stderr.write(f'  ✗ Chyba: {e}')
