from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from club.models import Club
from event.models import Entry, EntryClasses, EntryForeign, Event
from event.services.payments import (
    enrich_cart_entries,
    get_recent_pending_entries,
    remove_conflicting_cart_entries,
)
from event.views.entry_helpers import (
    build_public_entry_rows,
    sync_paid_foreign_riders,
    validate_foreign_summary_payload,
)
from rider.models import Rider
from rider.models import ForeignRider


User = get_user_model()


class EventEntryWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            first_name="Entry",
            last_name="Tester",
            username="entry_tester",
            email="entry_tester@example.com",
            password="StrongPass123!",
        )
        self.user.is_active = True
        self.user.save()

        self.club = Club.objects.create(team_name="Test Club")
        self.entry_classes = EntryClasses.objects.create(
            event_name="Test classes",
            beginners_1="Beginners 1",
            beginners_2="Beginners 2",
            beginners_3="Beginners 3",
            beginners_4="Beginners 4",
            boys_6="Boys 6",
            girls_6="Girls 6",
            cr_boys_12_and_under="Boys 12 and under",
        )
        self.event = Event.objects.create(
            name="Test race",
            date=date.today() + timedelta(days=30),
            organizer=self.club,
            classes_and_fees_like=self.entry_classes,
            reg_open=True,
            reg_open_from=timezone.now() - timedelta(days=1),
            reg_open_to=timezone.now() + timedelta(days=1),
            type_for_ranking="Volný závod",
        )
        self.rider = Rider.objects.create(
            uci_id=12345678901,
            first_name="Rider",
            last_name="Test",
            gender="Muž",
            date_of_birth=date(2018, 1, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            class_20="Boys 6",
            class_24="Boys 12 and under",
            class_beginner="Beginners 1",
        )

    def test_entry_page_loads_for_logged_in_user(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("event:entry", kwargs={"pk": self.event.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["event"].pk, self.event.pk)
        self.assertContains(response, "Přihlášení na závody")

    def test_entry_page_loads_without_season_settings(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("event:entry", kwargs={"pk": self.event.pk}))

        self.assertEqual(response.status_code, 200)


class Custom404Tests(TestCase):
    @override_settings(DEBUG=False)
    def test_unknown_route_returns_custom_404_page(self):
        response = self.client.get("/this-page-does-not-exist/")

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Stránka nebyla nalezena", status_code=404)


class PaymentServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            first_name="Payment",
            last_name="Tester",
            username="payment_tester",
            email="payment_tester@example.com",
            password="StrongPass123!",
        )
        self.user.is_active = True
        self.user.save()

        self.other_user = User.objects.create_user(
            first_name="Other",
            last_name="User",
            username="other_user",
            email="other_user@example.com",
            password="StrongPass123!",
        )
        self.other_user.is_active = True
        self.other_user.save()

        self.club = Club.objects.create(team_name="Payment Club")
        self.entry_classes = EntryClasses.objects.create(
            event_name="Payment classes",
            beginners_1="Beginners 1",
            boys_6="Boys 6",
            cr_boys_12_and_under="Boys 12 and under",
        )
        self.event = Event.objects.create(
            name="Payment race",
            date=date.today() + timedelta(days=30),
            organizer=self.club,
            classes_and_fees_like=self.entry_classes,
            reg_open=True,
            reg_open_from=timezone.now() - timedelta(days=1),
            reg_open_to=timezone.now() + timedelta(days=1),
            type_for_ranking="Volný závod",
        )
        self.rider = Rider.objects.create(
            uci_id=12345678999,
            first_name="Payment",
            last_name="Rider",
            gender="Muž",
            date_of_birth=date(2018, 1, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            class_20="Boys 6",
            class_24="Boys 12 and under",
            class_beginner="Beginners 1",
        )

    def test_get_recent_pending_entries_uses_24_hour_window(self):
        fresh_entry = Entry.objects.create(
            user=self.user,
            event=self.event,
            rider=self.rider,
            is_20=True,
            class_20="Boys 6",
            fee_20=300,
        )
        stale_entry = Entry.objects.create(
            user=self.user,
            event=self.event,
            rider=self.rider,
            is_24=True,
            class_24="Boys 12 and under",
            fee_24=350,
        )
        old_timestamp = timezone.now() - timedelta(days=2)
        Entry.objects.filter(pk=stale_entry.pk).update(transaction_date=old_timestamp)

        recent_ids = list(get_recent_pending_entries().values_list("id", flat=True))

        self.assertIn(fresh_entry.id, recent_ids)
        self.assertNotIn(stale_entry.id, recent_ids)

    def test_remove_conflicting_cart_entries_deletes_duplicate_only_once(self):
        first_entry = Entry.objects.create(
            user=self.user,
            event=self.event,
            rider=self.rider,
            is_20=True,
            class_20="Boys 6",
            fee_20=300,
        )
        duplicate_entry = Entry.objects.create(
            user=self.user,
            event=self.event,
            rider=self.rider,
            is_20=True,
            class_20="Boys 6",
            fee_20=300,
        )

        duplicates = remove_conflicting_cart_entries(
            Entry.objects.filter(pk__in=[first_entry.pk, duplicate_entry.pk]).order_by("id")
        )

        self.assertEqual([entry.pk for entry in duplicates], [duplicate_entry.pk])
        self.assertTrue(Entry.objects.filter(pk=first_entry.pk).exists())
        self.assertFalse(Entry.objects.filter(pk=duplicate_entry.pk).exists())

    def test_remove_conflicting_cart_entries_removes_entry_when_other_user_has_same_slot(self):
        foreign_cart_entry = Entry.objects.create(
            user=self.other_user,
            event=self.event,
            rider=self.rider,
            is_20=True,
            class_20="Boys 6",
            fee_20=300,
        )
        user_entry = Entry.objects.create(
            user=self.user,
            event=self.event,
            rider=self.rider,
            is_20=True,
            class_20="Boys 6",
            fee_20=300,
        )

        duplicates = remove_conflicting_cart_entries(Entry.objects.filter(pk=user_entry.pk))

        self.assertEqual([entry.pk for entry in duplicates], [user_entry.pk])
        self.assertTrue(Entry.objects.filter(pk=foreign_cart_entry.pk).exists())
        self.assertFalse(Entry.objects.filter(pk=user_entry.pk).exists())

    def test_enrich_cart_entries_sets_display_class_and_total(self):
        beginner_entry = Entry.objects.create(
            user=self.user,
            event=self.event,
            rider=self.rider,
            is_beginner=True,
            class_beginner="Beginners 1",
            fee_beginner=200,
        )
        cruiser_entry = Entry.objects.create(
            user=self.user,
            event=self.event,
            rider=self.rider,
            is_24=True,
            class_24="Boys 12 and under",
            fee_24=350,
        )
        orders = list(Entry.objects.filter(pk__in=[beginner_entry.pk, cruiser_entry.pk]).order_by("id"))

        total_price = enrich_cart_entries(orders)

        self.assertEqual(total_price, 550)
        self.assertEqual(orders[0].event_class, "Beginners 1")
        self.assertEqual(orders[1].event_class, "Boys 12 and under")


class ForeignEntryHelperTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(team_name="Foreign Club")
        self.entry_classes = EntryClasses.objects.create(
            event_name="Foreign classes",
            boys_6="Boys 6",
            cr_boys_12_and_under="Cruiser 12 and under",
        )
        self.event = Event.objects.create(
            name="Foreign race",
            date=date.today() + timedelta(days=20),
            organizer=self.club,
            classes_and_fees_like=self.entry_classes,
            reg_open=True,
            reg_open_from=timezone.now() - timedelta(days=1),
            reg_open_to=timezone.now() + timedelta(days=1),
            type_for_ranking="Volný závod",
        )

    def test_validate_foreign_summary_payload_requires_date_of_birth(self):
        payload = {
            "customer_email": "foreign@example.com",
            "rows": [
                {
                    "first_name": "Anna",
                    "last_name": "Smith",
                    "uci_id": "12345678901",
                    "date_of_birth": "",
                    "plate": "12",
                    "category_20": True,
                    "category_24": False,
                }
            ],
        }

        self.assertFalse(validate_foreign_summary_payload(payload))

    def test_build_public_entry_rows_marks_foreign_entries(self):
        foreign_entry = EntryForeign.objects.create(
            event=self.event,
            transaction_id="sess_123",
            first_name="Péter",
            last_name="Balogh",
            uci_id="10115844151",
            gender="Muž",
            nationality="HUN",
            plate="15",
            is_20=True,
            class_20="Elite 17+",
            fee_20=400,
            payment_complete=True,
        )

        rows = build_public_entry_rows([foreign_entry], is_foreign=True)

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].is_foreign)
        self.assertEqual(rows[0].club, "HUN")
        self.assertEqual(rows[0].category, "Elite 17+")

    def test_sync_paid_foreign_riders_creates_missing_foreign_rider(self):
        EntryForeign.objects.create(
            event=self.event,
            transaction_id="sess_sync",
            first_name="Péter",
            last_name="Balogh",
            uci_id="10115844151",
            date_of_birth=date(1980, 7, 8),
            gender="Muž",
            nationality="HUN",
            plate="15",
            transponder_20="TR-20",
            transponder_24="TR-24",
            is_24=True,
            class_24="Cruiser",
            fee_24=400,
            payment_complete=True,
        )

        sync_paid_foreign_riders(self.event, "sess_sync")

        foreign_rider = ForeignRider.objects.get(uci_id=10115844151)
        self.assertEqual(foreign_rider.first_name, "Péter")
        self.assertEqual(foreign_rider.state, "HUN")
        self.assertEqual(foreign_rider.class_24, "Cruiser")


class BalanceRecalculationViewTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            first_name="Staff",
            last_name="Tester",
            username="staff_tester",
            email="staff_tester@example.com",
            password="StrongPass123!",
        )
        self.staff_user.is_active = True
        self.staff_user.is_staff = True
        self.staff_user.save()

    @patch("event.views.views_payment.recalculate_all_balances")
    def test_recalculate_balances_view_renders_status_page(self, recalculate_mock):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("event:recalculate_balances_view"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kontrola kreditu")
        self.assertContains(response, "Stavy kreditů byly úspěšně překontrolovány.")
        recalculate_mock.assert_called_once()
