from datetime import date, timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from club.models import Club
from event.models import Entry, EntryClasses, EntryForeign, Event
from rider.models import Rider


class RecalculateEntryClassesCommandTests(TestCase):
    """Pardubice 11. 10. 2026: přihlášky se starými názvy kategorií po změně sady."""

    def setUp(self):
        self.club = Club.objects.create(team_name="TJ BMX Pardubice")
        self.classes = EntryClasses.objects.create(
            event_name="Pardubice 2026",
            boys_8="Boys 8-9",
            boys_9="Boys 8-9",
            men_junior="JM-U23-EM",
            men_u23="JM-U23-EM",
            men_elite="JM-U23-EM",
        )
        self.event = Event.objects.create(
            name="40. ročník O štít města Pardubice", date=self._datum_zavodu(),
            organizer=self.club, classes_and_fees_like=self.classes,
            reg_open=True, reg_open_from=timezone.now() - timedelta(days=10),
            reg_open_to=timezone.now() + timedelta(days=1), type_for_ranking="Volný závod",
        )
        self.elite = Rider.objects.create(
            uci_id=10000000051, first_name="Jiří", last_name="Weiner", gender="Muž",
            date_of_birth=date(2000, 1, 1), club=self.club, is_active=True, is_approved=True,
            is_elite=True, class_20="Men Elite",
        )
        self.boy = Rider.objects.create(
            uci_id=10000000069, first_name="Matyáš", last_name="Blasl", gender="Muž",
            date_of_birth=date(date.today().year - 8, 1, 1), club=self.club, is_active=True, is_approved=True,
            class_20="Boys 8",
        )
        self.stara_elite = Entry.objects.create(
            event=self.event, rider=self.elite, is_20=True, class_20="JM/U23/EM", fee_20=500, payment_complete=True,
        )
        self.stary_boy = Entry.objects.create(
            event=self.event, rider=self.boy, is_20=True, class_20="Boys 7/8", fee_20=300, payment_complete=True,
        )

    @staticmethod
    def _datum_zavodu():
        """Nadcházející den v letošní sezóně (31. 12. je poslední možný)."""
        dnes = date.today()
        return min(dnes + timedelta(days=2), date(dnes.year, 12, 31))

    def spust(self, *args):
        out = StringIO()
        call_command("recalculate_entry_classes", self.event.pk, *args, stdout=out)
        return out.getvalue()

    def test_nahled_nic_nezmeni(self):
        vystup = self.spust()

        self.assertIn("JM/U23/EM → JM-U23-EM", vystup)
        self.assertIn("Boys 7/8 → Boys 8-9", vystup)
        self.assertIn("Náhled: 2 přihlášek", vystup)
        self.stara_elite.refresh_from_db()
        self.assertEqual(self.stara_elite.class_20, "JM/U23/EM")

    def test_apply_prepise_kategorie_a_nemeni_startovne(self):
        vystup = self.spust("--apply")

        self.assertIn("Zapsáno: 2 přihlášek.", vystup)
        self.stara_elite.refresh_from_db()
        self.stary_boy.refresh_from_db()
        self.assertEqual(self.stara_elite.class_20, "JM-U23-EM")
        self.assertEqual(self.stary_boy.class_20, "Boys 8-9")
        self.assertEqual((self.stara_elite.fee_20, self.stary_boy.fee_20), (500, 300))
        self.assertIn("Všechny přihlášky mají kategorii podle aktuální sady.", self.spust())

    def test_nezaplacene_a_odbavene_prihlasky_nechava(self):
        nezaplacena = Entry.objects.create(
            event=self.event, rider=self.elite, is_20=True, class_20="JM/U23/EM", fee_20=500, payment_complete=False,
        )

        self.spust("--apply")

        nezaplacena.refresh_from_db()
        self.assertEqual(nezaplacena.class_20, "JM/U23/EM")

    def test_zahranicni_s_neznamou_kategorii_jen_nahlasi(self):
        EntryForeign.objects.create(
            event=self.event, first_name="Péter", last_name="Balogh", date_of_birth=date(1990, 1, 1),
            uci_id="10115844151", gender="Muž", nationality="HUN", is_20=True, class_20="Elite Men",
            fee_20=500, payment_complete=True,
        )

        vystup = self.spust("--apply")

        self.assertIn("zahraniční Péter Balogh", vystup)
        self.assertEqual(EntryForeign.objects.get().class_20, "Elite Men")

    def test_zavod_bez_sady_kategorii_odmitne(self):
        self.event.classes_and_fees_like = None
        self.event.save(update_fields=["classes_and_fees_like"])

        with self.assertRaisesMessage(CommandError, "nemá nastavenou sadu"):
            self.spust()

    def test_probehly_zavod_odmitne(self):
        self.event.date = date.today() - timedelta(days=1)
        self.event.save(update_fields=["date"])

        with self.assertRaisesMessage(CommandError, "nadcházejícího závodu"):
            self.spust("--apply")
        self.stara_elite.refresh_from_db()
        self.assertEqual(self.stara_elite.class_20, "JM/U23/EM")
