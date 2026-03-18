from datetime import date, timedelta
import os
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from club.models import Club
from event.models import CreditTransaction, Entry, EntryClasses, EntryForeign, Event, SeasonSettings, RaceRun, Result
from event.func import SetResults
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
from rider.rider import RiderQualifyToCNThread, should_recount_cn_qualification_for_event


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

    def test_mcr_entry_rejects_unqualified_rider_for_20_and_24(self):
        self.client.force_login(self.user)
        SeasonSettings.objects.create(year=date.today().year, qualify_to_cn=2)
        self.event.type_for_ranking = "Mistrovství ČR jednotlivců"
        self.event.save(update_fields=["type_for_ranking"])

        response = self.client.post(
            reverse("event:entry", kwargs={"pk": self.event.pk}),
            {
                "btn_add": "1",
                "checkbox_20": str(self.rider.uci_id),
                "checkbox_24": str(self.rider.uci_id),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("event:events"))
        self.assertFalse(
            Entry.objects.filter(event=self.event, rider=self.rider, is_20=True).exists()
        )
        self.assertFalse(
            Entry.objects.filter(event=self.event, rider=self.rider, is_24=True).exists()
        )

    def test_entry_rejects_elite_rider_for_24_category(self):
        self.client.force_login(self.user)
        self.rider.is_elite = True
        self.rider.save(update_fields=["is_elite"])

        response = self.client.post(
            reverse("event:entry", kwargs={"pk": self.event.pk}),
            {
                "btn_add": "1",
                "checkbox_24": str(self.rider.uci_id),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("event:events"))
        self.assertFalse(
            Entry.objects.filter(event=self.event, rider=self.rider, is_24=True).exists()
        )

    def test_historical_czech_cup_does_not_recount_current_year_cn_qualification(self):
        previous_year = date.today().year - 1
        SeasonSettings.objects.create(year=previous_year, qualify_to_cn=1)

        old_championship = Event.objects.create(
            name="Old championship",
            date=date(previous_year, 9, 1),
            organizer=self.club,
            type_for_ranking="Mistrovství ČR jednotlivců",
        )
        old_cup = Event.objects.create(
            name="Old cup",
            date=date(previous_year, 5, 1),
            organizer=self.club,
            type_for_ranking="Český pohár",
        )

        self.rider.is_qualify_to_cn_20 = True
        self.rider.is_qualify_to_cn_24 = False
        self.rider.save(update_fields=["is_qualify_to_cn_20", "is_qualify_to_cn_24"])

        self.assertFalse(should_recount_cn_qualification_for_event(old_cup))

        RiderQualifyToCNThread(year=previous_year).run()

        self.rider.refresh_from_db()
        self.assertTrue(self.rider.is_qualify_to_cn_20)
        self.assertFalse(self.rider.is_qualify_to_cn_24)


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

    @patch("event.views.payment_helpers.stripe.checkout.Session.retrieve")
    def test_success_view_confirms_exact_session_even_when_entry_is_older_than_24_hours(self, retrieve_mock):
        self.client.force_login(self.user)
        entry = Entry.objects.create(
            user=self.user,
            event=self.event,
            rider=self.rider,
            transaction_id="sess_exact_entry",
            is_20=True,
            class_20="Boys 6",
            fee_20=300,
        )
        Entry.objects.filter(pk=entry.pk).update(
            transaction_date=timezone.now() - timedelta(days=3)
        )
        retrieve_mock.return_value = {
            "payment_status": "paid",
            "customer_details": {
                "name": "Exact Buyer",
                "email": "exact@example.com",
            },
        }

        response = self.client.get(
            reverse("event:success", kwargs={"pk": self.event.pk})
            + "?session_id=sess_exact_entry"
        )

        self.assertEqual(response.status_code, 200)
        entry.refresh_from_db()
        self.assertTrue(entry.payment_complete)
        self.assertEqual(entry.customer_email, "exact@example.com")

    @patch("event.views.payment_helpers.stripe.checkout.Session.retrieve")
    def test_success_credit_view_confirms_exact_session(self, retrieve_mock):
        self.client.force_login(self.user)
        credit_transaction = CreditTransaction.objects.create(
            user=self.user,
            amount=700,
            transaction_id="sess_credit_exact",
        )
        retrieve_mock.return_value = {
            "payment_status": "paid",
            "payment_intent": "pi_credit_exact",
        }

        response = self.client.get(
            reverse("event:success-credit") + "?session_id=sess_credit_exact"
        )

        self.assertRedirects(response, reverse("event:success-credit-update"))
        credit_transaction.refresh_from_db()
        self.user.refresh_from_db()
        self.assertTrue(credit_transaction.payment_complete)
        self.assertEqual(credit_transaction.payment_intent, "pi_credit_exact")
        self.assertEqual(self.user.credit, 700)


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

    @patch("event.views.payment_helpers._construct_stripe_event")
    def test_webhook_marks_foreign_entries_paid(self, construct_event_mock):
        foreign_entry = EntryForeign.objects.create(
            event=self.event,
            transaction_id="sess_foreign_webhook",
            first_name="Péter",
            last_name="Balogh",
            uci_id="10115844151",
            gender="Muž",
            nationality="HUN",
            club="",
            transponder="TR-20",
            is_20=True,
            class_20="Elite 17+",
            fee_20=400,
            payment_complete=False,
        )
        construct_event_mock.return_value = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "sess_foreign_webhook",
                    "payment_status": "paid",
                    "payment_intent": "pi_foreign",
                    "customer_details": {
                        "name": "Foreign Buyer",
                        "email": "foreign@example.com",
                    },
                }
            },
        }

        response = self.client.post(
            reverse("event:stripe-credit-webhook"),
            data="{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="sig_test",
        )

        self.assertEqual(response.status_code, 200)
        foreign_entry.refresh_from_db()
        self.assertTrue(foreign_entry.payment_complete)
        self.assertEqual(foreign_entry.customer_email, "foreign@example.com")


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


class RemResultsImportTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(team_name="Import Club")
        self.event = Event.objects.create(
            name="REM Import Race",
            date=date(2025, 4, 13),
            organizer=self.club,
            reg_open=False,
            type_for_ranking="Český pohár",
        )
        self.rider = Rider.objects.create(
            uci_id=10125224253,
            first_name="Simon",
            last_name="Aksamit",
            gender="Muž",
            date_of_birth=date(2009, 8, 2),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            class_20="Boys 15",
            class_24="Boys 15 and 16",
        )

    def test_import_file_creates_results_and_race_runs_in_single_pass(self):
        rem_tsv = "\t".join(
            [
                "EVENT_NAME", "FIRST_NAME", "LAST_NAME", "CLUB", "CLASS", "REGISTRATION_CLASS", "TEAM", "SEX",
                "BIRTHDATE", "MAIL", "TYPE", "LICENCE_TYPE", "UCIID", "UCIID_EXP_DATE", "INTERNAL_IDENT", "STATUS",
                "PLATE", "TRANSPONDER", "ENTRY_PAYED", "PAYMENT_AMOUNT", "ADMIN_FEE", "TRANSPONDER_HIRE_PRICE",
                "TRANSPONDER_HIRE_FLAG", "PAYMENT_CURR", "PAYMENT_TYPE", "CLASS_RANKING", "MOTO1_GATE", "MOTO1_LANE",
                "MOTO1_PLACE", "MOTO1_RACE_POINTS", "MOTO1_MOTO_POINTS", "MOTO1_HILL_TIME", "MOTO1_INTER2_TIME", "MOTO1_TIME", "MOTO2_GATE", "MOTO2_LANE",
                "MOTO2_PLACE", "MOTO2_RACE_POINTS", "MOTO2_MOTO_POINTS", "MOTO2_TIME", "FINAL_SUBTYPE", "FINAL_GATE",
                "FINAL_LANE", "FINAL_PLACE", "FINAL_RACE_POINTS", "FINAL_MOTO_POINTS", "FINAL_INTER2_TIME", "FINAL_TIME", "F2_GATE",
                "F2_LANE", "F2_PLACE", "F2_RACE_POINTS", "F2_MOTO_POINTS", "F2_HILL_TIME", "F2_INTER2_TIME", "F2_TIME",
            ]
        )
        rem_row = "\t".join(
            [
                "2. zavod SAZKA Ceskeho poharu", "Simon", "Aksamit", "Import Club", "Boys 15-16", "Boys 15-16", "",
                "M", "02-08-2009", "simon@example.com", "C", "U", "10125224253", "31-12-2025", "", "S", "868",
                "HW-43726", "X", "500.00", "0.00", "0.00", "false", "CZK", "P", "7", "40", "1", "1st", "8", "1", "1.921",
                "12.441", "29.224", "83", "7", "2nd", "7", "2", "29.753", "A", "11", "3", "7th", "10", "7", "12.883",
                "30.798", "18", "4", "2nd", "0", "2", "1.877", "12.517", "29.446",
            ]
        )

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
            handle.write(rem_tsv)
            handle.write("\n")
            handle.write(rem_row)
            file_path = handle.name

        try:
            SetResults.import_file(self.event.id, file_path)
        finally:
            os.unlink(file_path)

        result = Result.objects.get(event=self.event, rider=self.rider)
        self.assertEqual(result.place, 7)
        self.assertEqual(result.points, 75)

        runs = RaceRun.objects.filter(result=result).order_by("round_type", "round_number")
        self.assertEqual(runs.count(), 4)
        self.assertTrue(runs.filter(round_type="MOTO", round_number=1, place="1st", hill_time=1.921, split_1=12.441, finish_time=29.224).exists())
        self.assertTrue(runs.filter(round_type="MOTO", round_number=2, place="2nd", finish_time=29.753).exists())
        self.assertTrue(runs.filter(round_type="FINAL", place="7th", split_1=12.883, finish_time=30.798).exists())
        self.assertTrue(runs.filter(round_type="F2", place="2nd", hill_time=1.877, split_1=12.517, finish_time=29.446).exists())
