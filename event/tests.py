from datetime import date, timedelta
from io import BytesIO
import os
import tempfile
import zipfile
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django_ckeditor_5.widgets import CKEditor5Widget
from openpyxl import Workbook, load_workbook
from PIL import Image
from commissar.models import Commissar
from reportlab.pdfgen import canvas

from club.models import Club
from event.forms import EventPropositionForm
from event.models import CreditTransaction, Entry, EntryClasses, EntryForeign, Event, SeasonSettings, RaceRun, Result
from event.func import SetResults
from event.services.race_run_import import RaceRunImportService
from event.services.uci_export import build_uci_export_rows, generate_uci_export_zip
from event.services.payments import (
    enrich_cart_entries,
    get_recent_pending_entries,
    remove_conflicting_cart_entries,
)
from event.views.entry_helpers import (
    build_public_entry_rows,
    enrich_foreign_summary_rows,
    sync_paid_foreign_riders,
    validate_foreign_summary_payload,
)
from accounts.models import Account
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

    def test_validate_foreign_summary_payload_rejects_championship_with_cruiser(self):
        payload = {
            "customer_email": "foreign@example.com",
            "rows": [
                {
                    "first_name": "Anna",
                    "last_name": "Smith",
                    "uci_id": "12345678901",
                    "date_of_birth": "2010-01-01",
                    "plate": "12",
                    "championship": True,
                    "cruiser": True,
                }
            ],
        }

        self.assertFalse(validate_foreign_summary_payload(payload))

    def test_enrich_foreign_summary_rows_supports_challenge_and_cruiser(self):
        summary_rows, total_fee = enrich_foreign_summary_rows(
            self.event,
            [
                {
                    "first_name": "Anna",
                    "last_name": "Smith",
                    "uci_id": "12345678901",
                    "date_of_birth": "2020-01-01",
                    "sex": "Muž",
                    "plate": "12",
                    "challenge": True,
                    "cruiser": True,
                }
            ],
        )

        self.assertEqual(len(summary_rows), 1)
        self.assertEqual(summary_rows[0]["selected_categories"], ["Challenge", "Cruiser"])
        self.assertEqual(summary_rows[0]["class_20"], "Boys 6")
        self.assertEqual(summary_rows[0]["class_24"], "Cruiser 12 and under")
        self.assertEqual(summary_rows[0]["fee_20"], 0)
        self.assertEqual(summary_rows[0]["fee_24"], 0)
        self.assertEqual(total_fee, 0)

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

    def test_build_public_entry_rows_returns_both_categories_for_single_entry(self):
        foreign_entry = EntryForeign.objects.create(
            event=self.event,
            transaction_id="sess_multi",
            first_name="David",
            last_name="Průša",
            uci_id="10047037910",
            gender="Muž",
            nationality="CZE",
            plate="0",
            is_20=True,
            is_24=True,
            class_20="Master 30+",
            class_24="Cruiser",
            fee_20=400,
            fee_24=400,
            payment_complete=True,
        )

        rows = build_public_entry_rows([foreign_entry], is_foreign=True)

        self.assertEqual(len(rows), 2)
        self.assertEqual({row.category for row in rows}, {"Master 30+", "Cruiser"})

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

    def test_import_file_creates_only_results(self):
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
        self.assertFalse(RaceRun.objects.filter(result=result).exists())


class UciExportTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            first_name="UCI",
            last_name="Staff",
            username="uci_staff",
            email="uci_staff@example.com",
            password="StrongPass123!",
        )
        self.staff_user.is_active = True
        self.staff_user.is_staff = True
        self.staff_user.save()

        self.club = Club.objects.create(team_name="UCI Club")
        self.event = Event.objects.create(
            name="UCI Combined Race",
            date=date(2025, 6, 1),
            organizer=self.club,
            reg_open=False,
            type_for_ranking="Český pohár",
            is_uci_race=True,
            uci_event_code="D2EV268824",
            uci_code_women_elite="WE123",
            uci_code_men_elite="ME123",
            uci_code_women_under_23="WU23123",
            uci_code_men_under_23="MU23123",
            uci_code_women_junior="WJ123",
            uci_code_men_junior="MJ123",
        )

        self.men_u23 = Rider.objects.create(
            uci_id=10000000001,
            first_name="Adam",
            last_name="U23",
            gender="Muž",
            date_of_birth=date(2004, 1, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            is_elite=True,
            plate=101,
        )
        self.men_elite_best = Rider.objects.create(
            uci_id=10000000002,
            first_name="Boris",
            last_name="Elite",
            gender="Muž",
            date_of_birth=date(1998, 1, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            is_elite=True,
            plate=202,
        )
        self.men_elite_second = Rider.objects.create(
            uci_id=10000000003,
            first_name="Cyril",
            last_name="Elite",
            gender="Muž",
            date_of_birth=date(1995, 1, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            is_elite=True,
            plate=303,
        )

        self.u23_result = Result.objects.create(
            event=self.event,
            rider=self.men_u23,
            date=self.event.date,
            event_type=self.event.type_for_ranking,
            organizer=self.club.team_name,
            category="Combined Men",
            place=1,
            points=100,
            is_20=True,
        )
        self.elite_best_result = Result.objects.create(
            event=self.event,
            rider=self.men_elite_best,
            date=self.event.date,
            event_type=self.event.type_for_ranking,
            organizer=self.club.team_name,
            category="Combined Men",
            place=4,
            points=70,
            is_20=True,
        )
        self.elite_second_result = Result.objects.create(
            event=self.event,
            rider=self.men_elite_second,
            date=self.event.date,
            event_type=self.event.type_for_ranking,
            organizer=self.club.team_name,
            category="Combined Men",
            place=5,
            points=60,
            is_20=True,
        )

        RaceRun.objects.create(
            result=self.u23_result,
            event=self.event,
            rider=self.men_u23,
            is_20=True,
            is_beginner=False,
            round_type="FINAL",
            finish_time=31.111,
        )
        RaceRun.objects.create(
            result=self.elite_best_result,
            event=self.event,
            rider=self.men_elite_best,
            is_20=True,
            is_beginner=False,
            round_type="FINAL",
            finish_time=33.333,
        )
        RaceRun.objects.create(
            result=self.elite_second_result,
            event=self.event,
            rider=self.men_elite_second,
            is_20=True,
            is_beginner=False,
            round_type="FINAL",
            finish_time=34.444,
        )

    def _create_uci_template(self):
        temp_dir = tempfile.mkdtemp()
        template_path = os.path.join(temp_dir, "uci-template.xlsx")
        workbook = Workbook()
        general_ws = workbook.active
        general_ws.title = "General"
        general_ws["A4"] = "Competition Code"
        general_ws["A5"] = "Event Code"
        results_ws = workbook.create_sheet("Results")
        headers = ["Rank", "BIB", "UCI ID", "Last Name", "First Name", "Country", "Team", "Gender", "Phase", "Heat", "Result", "IRM"]
        for index, header in enumerate(headers, start=1):
            results_ws.cell(1, index, header)
        workbook.create_sheet("Reference")
        workbook.create_sheet("Country Reference")
        workbook.save(template_path)
        return temp_dir, template_path

    def test_uci_export_creates_six_files_and_recalculates_rank_within_each_uci_group(self):
        self.client.force_login(self.staff_user)
        temp_dir, template_path = self._create_uci_template()

        try:
            with patch("event.views.views_admin.UCI_EXPORT_TEMPLATE", template_path):
                response = self.client.get(reverse("event:export_uci_results", kwargs={"event_id": self.event.id}))
        finally:
            for filename in os.listdir(temp_dir):
                os.remove(os.path.join(temp_dir, filename))
            os.rmdir(temp_dir)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")

        archive = zipfile.ZipFile(BytesIO(response.content))
        filenames = sorted(archive.namelist())
        self.assertEqual(len(filenames), 6)
        self.assertTrue(any("men_elite" in name for name in filenames))
        self.assertTrue(any("men_u23" in name for name in filenames))

        men_elite_name = next(name for name in filenames if "men_elite" in name)
        men_u23_name = next(name for name in filenames if "men_u23" in name)

        men_elite_workbook = load_workbook(BytesIO(archive.read(men_elite_name)))
        men_elite_results = men_elite_workbook["Results"]
        self.assertEqual(men_elite_results["A2"].value, 1)
        self.assertEqual(men_elite_results["C2"].value, self.men_elite_best.uci_id)
        self.assertEqual(men_elite_results["K2"].value, "1st, 33.333")
        self.assertEqual(men_elite_results["A3"].value, 2)
        self.assertEqual(men_elite_results["C3"].value, self.men_elite_second.uci_id)
        self.assertEqual(men_elite_results["K3"].value, "2nd, 34.444")

        men_u23_workbook = load_workbook(BytesIO(archive.read(men_u23_name)))
        men_u23_general = men_u23_workbook["General"]
        men_u23_results = men_u23_workbook["Results"]
        self.assertEqual(men_u23_general["B4"].value, "MU23123")
        self.assertEqual(men_u23_general["B5"].value, "D2EV268824")
        self.assertEqual(men_u23_results["A2"].value, 1)
        self.assertEqual(men_u23_results["C2"].value, self.men_u23.uci_id)

    def test_uci_export_redirects_with_flash_message_when_event_code_is_missing(self):
        self.client.force_login(self.staff_user)
        self.event.uci_event_code = ""
        self.event.save(update_fields=["uci_event_code"])
        temp_dir, template_path = self._create_uci_template()

        try:
            with patch("event.views.views_admin.UCI_EXPORT_TEMPLATE", template_path):
                response = self.client.get(
                    reverse("event:export_uci_results", kwargs={"event_id": self.event.id}),
                    follow=True,
                )
        finally:
            for filename in os.listdir(temp_dir):
                os.remove(os.path.join(temp_dir, filename))
            os.rmdir(temp_dir)

        self.assertRedirects(response, reverse("event:event-admin", kwargs={"pk": self.event.id}))
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("U závodu chybí UCI_EVENT_CODE.", messages)

    def test_uci_export_service_builds_rows_and_zip_metadata(self):
        rows = build_uci_export_rows(self.event, "Men Elite")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["rank"], 1)
        self.assertEqual(rows[0]["uci_id"], self.men_elite_best.uci_id)
        self.assertEqual(rows[0]["result"], "1st, 33.333")

        temp_dir, template_path = self._create_uci_template()
        try:
            zip_name, zip_bytes, export_metadata = generate_uci_export_zip(self.event, template_path)
        finally:
            for filename in os.listdir(temp_dir):
                os.remove(os.path.join(temp_dir, filename))
            os.rmdir(temp_dir)

        self.assertTrue(zip_name.endswith(".zip"))
        self.assertEqual(len(export_metadata), 6)
        self.assertTrue(any(item["slug"] == "men_elite" and item["rows"] == 2 for item in export_metadata))

        archive = zipfile.ZipFile(BytesIO(zip_bytes))
        self.assertEqual(len(archive.namelist()), 6)


class EuropeanCupAdminTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            first_name="EC",
            last_name="Admin",
            username="ec_admin",
            email="ec_admin@example.com",
            password="StrongPass123!",
        )
        self.staff_user.is_staff = True
        self.staff_user.is_active = True
        self.staff_user.save(update_fields=["is_staff", "is_active"])

        self.club = Club.objects.create(team_name="European Club")
        self.event = Event.objects.create(
            name="UEC BMX Racing European Cup - Round 1",
            date=date.today() + timedelta(days=10),
            organizer=self.club,
            type_for_ranking="Evropský pohár",
            reg_open=False,
        )

    def _make_pdf_upload(self, filename="results.pdf", text="results"):
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer)
        pdf.drawString(100, 750, text)
        pdf.showPage()
        pdf.save()
        return SimpleUploadedFile(filename, buffer.getvalue(), content_type="application/pdf")

    def test_ec_admin_get_does_not_generate_exports(self):
        self.client.force_login(self.staff_user)

        with patch("event.views.views_admin._generate_ec_file") as generate_ec_file_mock, patch(
            "event.views.views_admin.generate_insurance_file"
        ) as generate_insurance_file_mock:
            response = self.client.get(reverse("event:event-admin", kwargs={"pk": self.event.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "btn-generate-ec-file")
        self.assertContains(response, "btn-generate-ec-insurance-file")
        generate_ec_file_mock.assert_not_called()
        generate_insurance_file_mock.assert_not_called()

    def test_ec_admin_generate_ec_file_runs_only_on_explicit_post(self):
        self.client.force_login(self.staff_user)

        with patch("event.views.views_admin._generate_ec_file") as generate_ec_file_mock:
            response = self.client.post(
                reverse("event:event-admin", kwargs={"pk": self.event.id}),
                {"btn-generate-ec-file": "1"},
            )

        self.assertEqual(response.status_code, 200)
        generate_ec_file_mock.assert_called_once_with(self.event)

    def test_ec_admin_rejects_non_pdf_results_upload(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("event:event-admin", kwargs={"pk": self.event.id}),
            {
                "btn-upload-ec-results-pdf": "1",
                "results-pdf-files": SimpleUploadedFile(
                    "results.txt",
                    b"not-a-pdf",
                    content_type="text/plain",
                ),
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("event:event-admin", kwargs={"pk": self.event.id}))
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertTrue(any("mus\u00ed b\u00fdt PDF soubor" in message for message in messages))

    def test_ec_admin_accepts_single_pdf_results_upload(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("event:event-admin", kwargs={"pk": self.event.id}),
            {
                "btn-upload-ec-results-pdf": "1",
                "results-pdf-files": self._make_pdf_upload(),
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("event:event-admin", kwargs={"pk": self.event.id}))
        self.event.refresh_from_db()
        self.assertTrue(bool(self.event.full_results))
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("Výsledky byly nahrány a zveřejněny jako jedno sloučené PDF.", messages)

    def test_ec_admin_accepts_multiple_pdf_results_upload(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("event:event-admin", kwargs={"pk": self.event.id}),
            {
                "btn-upload-ec-results-pdf": "1",
                "results-pdf-files": [
                    self._make_pdf_upload("results-1.pdf", "block-1"),
                    self._make_pdf_upload("results-2.pdf", "block-2"),
                    self._make_pdf_upload("results-3.pdf", "block-3"),
                ],
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("event:event-admin", kwargs={"pk": self.event.id}))
        self.event.refresh_from_db()
        self.assertTrue(bool(self.event.full_results))
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("Výsledky byly nahrány a zveřejněny jako jedno sloučené PDF.", messages)


class EventPropositionEditorUploadTests(TestCase):
    def setUp(self):
        self.temp_media_dir = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.temp_media_dir.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.temp_media_dir.cleanup)

        self.club = Club.objects.create(team_name="Upload Club")

        self.club_manager = User.objects.create_user(
            first_name="Club",
            last_name="Manager",
            username="club_manager",
            email="club_manager@example.com",
            password="StrongPass123!",
        )
        self.club_manager.is_active = True
        self.club_manager.is_club_manager = True
        self.club_manager.club = self.club
        self.club_manager.save(update_fields=["is_active", "is_club_manager", "club"])

        self.regular_user = User.objects.create_user(
            first_name="Regular",
            last_name="User",
            username="regular_user",
            email="regular_user@example.com",
            password="StrongPass123!",
        )
        self.regular_user.is_active = True
        self.regular_user.save(update_fields=["is_active"])

    def _make_image_upload(self, name="editor-image.png", image_format="PNG"):
        buffer = BytesIO()
        image = Image.new("RGB", (32, 32), color=(12, 120, 220))
        image.save(buffer, format=image_format)
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def test_club_manager_can_upload_editor_image(self):
        self.client.force_login(self.club_manager)

        response = self.client.post(
            reverse("event:proposition-editor-upload"),
            {"upload": self._make_image_upload()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("url", response.json())
        self.assertIn("/media/proposition_uploads/", response.json()["url"])

    def test_regular_authenticated_user_cannot_upload_editor_image(self):
        self.client.force_login(self.regular_user)

        response = self.client.post(
            reverse("event:proposition-editor-upload"),
            {"upload": self._make_image_upload()},
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("error", response.json())

    def test_non_image_upload_is_rejected(self):
        self.client.force_login(self.club_manager)

        response = self.client.post(
            reverse("event:proposition-editor-upload"),
            {
                "upload": SimpleUploadedFile(
                    "editor-file.txt",
                    b"not-an-image",
                    content_type="text/plain",
                )
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())


class EventPropositionSanitizationTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(team_name="Sanitize Club")
        self.user = Account.objects.create_user(
            first_name="Event",
            last_name="Editor",
            username="event_editor",
            email="event_editor@example.com",
            password="StrongPass123!",
        )
        self.event = Event.objects.create(
            name="Sanitized Proposition Event",
            date=date.today() + timedelta(days=20),
            organizer=self.club,
            type_for_ranking="Volný závod",
        )

    def test_event_proposition_save_sanitizes_html_and_preserves_safe_media(self):
        from event.models import EventProposition

        proposition = EventProposition.objects.create(
            event=self.event,
            created_by=self.user,
            updated_by=self.user,
            summary=(
                '<p>Summary</p><iframe src="https://www.youtube.com/embed/x"></iframe>'
                '<a href="https://www.youtube.com/watch?v=abc" target="_blank">Video</a>'
                '<img src="/media/proposition_uploads/test.png" onerror="alert(1)" alt="Track map">'
            ),
        )

        self.assertNotIn("<iframe", proposition.summary)
        self.assertIn('href="https://www.youtube.com/watch?v=abc"', proposition.summary)
        self.assertIn('rel="noopener noreferrer"', proposition.summary)
        self.assertIn('src="/media/proposition_uploads/test.png"', proposition.summary)
        self.assertNotIn("onerror", proposition.summary)


class EventPropositionFormTests(TestCase):
    def test_event_proposition_form_uses_ckeditor5_for_rich_text_fields(self):
        form = EventPropositionForm()

        for field_name in EventPropositionForm.RICH_TEXT_FIELDS:
            self.assertIsInstance(form.fields[field_name].widget, CKEditor5Widget)


class CommissarAssignmentsTests(TestCase):
    def setUp(self):
        self.commission_user = User.objects.create_user(
            first_name="Komise",
            last_name="User",
            username="commission_user",
            email="commission@example.com",
            password="StrongPass123!",
        )
        self.commission_user.is_active = True
        self.commission_user.is_commission = True
        self.commission_user.save(update_fields=["is_active", "is_commission"])

        self.staff_user = User.objects.create_user(
            first_name="Staff",
            last_name="Viewer",
            username="staff_viewer",
            email="staff_viewer@example.com",
            password="StrongPass123!",
        )
        self.staff_user.is_active = True
        self.staff_user.is_staff = True
        self.staff_user.save(update_fields=["is_active", "is_staff"])

        self.superuser = User.objects.create_user(
            first_name="Super",
            last_name="User",
            username="super_user",
            email="super_user@example.com",
            password="StrongPass123!",
        )
        self.superuser.is_active = True
        self.superuser.is_superuser = True
        self.superuser.save(update_fields=["is_active", "is_superuser"])

        self.club = Club.objects.create(team_name="Commissar Club")
        self.pcp = Commissar.objects.create(first_name="Petr", last_name="Hlavni", is_active=True)
        self.assist = Commissar.objects.create(first_name="Alena", last_name="Asistent", is_active=True)
        self.start = Commissar.objects.create(first_name="Start", last_name="Komisar", is_active=True)

        self.event = Event.objects.create(
            name="Commissar Race",
            date=date(date.today().year, 7, 15),
            organizer=self.club,
            type_for_ranking="Český pohár",
            reg_open=False,
        )

    def test_commission_user_sees_edit_button(self):
        self.client.force_login(self.commission_user)

        response = self.client.get(reverse("event:commissar-assignments"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Editovat")

    def test_staff_user_can_view_but_not_edit(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("event:commissar-assignments"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Editovat")

    def test_superuser_sees_edit_button(self):
        self.client.force_login(self.superuser)

        response = self.client.get(reverse("event:commissar-assignments"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Editovat")

    def test_edit_mode_renders_sticky_change_bar(self):
        self.client.force_login(self.commission_user)

        response = self.client.get(
            f"{reverse('event:commissar-assignments')}?year={self.event.date.year}&edit=1"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "commissar-edit-sticky-bar")
        self.assertContains(response, "Neuložené změny")

    def test_commission_user_can_update_assignments_and_audit_is_logged(self):
        self.client.force_login(self.commission_user)

        with self.assertLogs("audit", level="INFO") as audit_logs:
            response = self.client.post(
                reverse("event:commissar-assignments"),
                {
                    "year": str(self.event.date.year),
                    f"pcp_{self.event.id}": str(self.pcp.id),
                    f"pcp_assist_{self.event.id}": str(self.assist.id),
                    f"start_commissar_{self.event.id}": "",
                },
                follow=True,
            )

        self.assertRedirects(
            response,
            f"{reverse('event:commissar-assignments')}?year={self.event.date.year}",
            fetch_redirect_response=False,
        )
        self.event.refresh_from_db()
        self.assertEqual(self.event.pcp_id, self.pcp.id)
        self.assertEqual(self.event.pcp_assist_id, self.assist.id)
        self.assertTrue(any("commissar_assignment_updated" in line for line in audit_logs.output))

    def test_same_commissar_cannot_hold_two_roles_in_one_event(self):
        self.client.force_login(self.commission_user)

        response = self.client.post(
            reverse("event:commissar-assignments"),
            {
                "year": str(self.event.date.year),
                f"pcp_{self.event.id}": str(self.pcp.id),
                f"pcp_assist_{self.event.id}": str(self.pcp.id),
                f"start_commissar_{self.event.id}": "",
            },
            follow=True,
        )

        self.assertRedirects(
            response,
            f"{reverse('event:commissar-assignments')}?year={self.event.date.year}&edit=1",
            fetch_redirect_response=False,
        )
        self.event.refresh_from_db()
        self.assertIsNone(self.event.pcp_id)
        self.assertIsNone(self.event.pcp_assist_id)
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertTrue(any("nemůže být jeden rozhodčí nasazen do více rolí" in message for message in messages))

    def test_conflicting_concurrent_edit_is_rejected(self):
        self.client.force_login(self.commission_user)
        self.event.pcp = self.start
        self.event.save(update_fields=["pcp"])

        response = self.client.post(
            reverse("event:commissar-assignments"),
            {
                "year": str(self.event.date.year),
                f"original_pcp_{self.event.id}": "",
                f"original_pcp_assist_{self.event.id}": "",
                f"original_start_commissar_{self.event.id}": "",
                f"pcp_{self.event.id}": str(self.pcp.id),
                f"pcp_assist_{self.event.id}": "",
                f"start_commissar_{self.event.id}": "",
            },
            follow=True,
        )

        self.assertRedirects(
            response,
            f"{reverse('event:commissar-assignments')}?year={self.event.date.year}&edit=1",
            fetch_redirect_response=False,
        )
        self.event.refresh_from_db()
        self.assertEqual(self.event.pcp_id, self.start.id)
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertTrue(any("mezitím upravil někdo jiný" in message for message in messages))

    def test_event_model_rejects_duplicate_commissar_roles(self):
        self.event.pcp = self.pcp
        self.event.pcp_assist = self.pcp

        with self.assertRaises(ValidationError):
            self.event.full_clean()


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class RaceRunImportServiceTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(team_name="Import Club")
        self.event = Event.objects.create(
            name="Stats Import Race",
            date=date(2025, 10, 25),
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
            plate_text="868",
        )
        self.result = Result.objects.create(
            event=self.event,
            date=self.event.date,
            event_type=self.event.type_for_ranking,
            organizer=self.club.team_name,
            rider=self.rider,
            first_name=self.rider.first_name,
            last_name=self.rider.last_name,
            club=self.club.team_name,
            category="Boys 15-16",
            place=7,
            points=75,
            is_beginner=False,
            is_20=True,
        )

    def test_import_event_runs_builds_race_runs_from_html_stats(self):
        target_dir = os.path.join(settings.MEDIA_ROOT, "event_stats", str(self.event.pk))
        if os.path.isdir(target_dir):
            for filename in os.listdir(target_dir):
                os.remove(os.path.join(target_dir, filename))
        os.makedirs(target_dir, exist_ok=True)

        motos_html = """<html><body>
        <table class="gridtable">
        <caption>Boys 15-16 (1 Riders)</caption>
        <tr><th>Plate</th><th>Club</th><th>Name</th><th>Moto 1</th><th>Moto 2</th></tr>
        <tr><td>868</td><td>Import Club</td><td>Simon Aksamit</td><td>40 / 1</td><td>83 / 7</td></tr>
        </table>
        </body></html>"""
        motos_results_html = """<html><body>
        <table class="gridtable">
        <caption>Boys 15-16 (1 Riders)</caption>
        <tr><th>Ranking</th><th>Plate</th><th>Club</th><th>Name</th><th>Moto-Points</th><th>Moto 1</th><th>Moto 2</th></tr>
        <tr><td>7</td><td>868</td><td>Import Club</td><td>Simon Aksamit</td><td>3</td><td>1st 1.921 / 12.441 / 29.224</td><td>2nd 1.955 / 12.700 / 29.753</td></tr>
        </table>
        </body></html>"""
        final_html = """<html><body>
        <table class="gridtable">
        <caption>Boys 15-16 (1 Riders)</caption>
        <tr><th>Final</th><th>Lane</th><th>Plate</th><th>Name</th><th>Club</th></tr>
        <tr><td>F1 (A)</td><td>Pick 3</td><td>868</td><td>Simon Aksamit</td><td>Import Club</td></tr>
        </table>
        </body></html>"""

        files = {
            "motos__sample.html": motos_html,
            "motos_results__sample.html": motos_results_html,
            "final__sample.html": final_html,
        }
        for filename, content in files.items():
            with open(os.path.join(target_dir, filename), "w", encoding="utf-8") as handle:
                handle.write(content)

        imported_runs = RaceRunImportService().import_event_runs(self.event)

        self.assertEqual(imported_runs, 3)
        moto_1 = RaceRun.objects.get(result=self.result, round_type="MOTO", round_number=1)
        self.assertEqual(moto_1.heat_code, "40")
        self.assertEqual(moto_1.lane, 1)
        self.assertEqual(moto_1.place, "1st")
        self.assertEqual(moto_1.hill_time, 1.921)
        self.assertEqual(moto_1.split_1, 12.441)
        self.assertEqual(moto_1.finish_time, 29.224)
        self.assertEqual(moto_1.category, "Boys 15-16")
        self.assertEqual(moto_1.plate, "868")

        moto_2 = RaceRun.objects.get(result=self.result, round_type="MOTO", round_number=2)
        self.assertEqual(moto_2.heat_code, "83")
        self.assertEqual(moto_2.lane, 7)
        self.assertEqual(moto_2.place, "2nd")
        self.assertEqual(moto_2.finish_time, 29.753)

        final_run = RaceRun.objects.get(result=self.result, round_type="FINAL")
        self.assertEqual(final_run.heat_code, "F1 (A)")
        self.assertEqual(final_run.lane, 3)

    def test_import_event_runs_parses_rem_finish_and_hill_format(self):
        target_dir = os.path.join(settings.MEDIA_ROOT, "event_stats", str(self.event.pk))
        if os.path.isdir(target_dir):
            for filename in os.listdir(target_dir):
                os.remove(os.path.join(target_dir, filename))
        os.makedirs(target_dir, exist_ok=True)

        motos_html = """<html><body>
        <table class="gridtable">
        <caption>Boys 15-16 (1 Riders)</caption>
        <tr><th>Plate</th><th>Club</th><th>Name</th><th>Moto 1</th></tr>
        <tr><td>868</td><td>Import Club</td><td>Simon Aksamit</td><td>40 / 1</td></tr>
        </table>
        </body></html>"""
        motos_results_html = """<html><body>
        <table class="gridtable">
        <caption>Boys 15-16 (1 Riders)</caption>
        <tr><th>Ranking</th><th>Plate</th><th>Club</th><th>Name</th><th>Moto-Points</th><th>Moto 1</th></tr>
        <tr><td>7</td><td>868</td><td>Import Club</td><td>Simon Aksamit</td><td>3</td><td>3rd<br><small>39,205<br>{1.753}</small></td></tr>
        </table>
        </body></html>"""

        files = {
            "motos__sample.html": motos_html,
            "motos_results__sample.html": motos_results_html,
        }
        for filename, content in files.items():
            with open(os.path.join(target_dir, filename), "w", encoding="utf-8") as handle:
                handle.write(content)

        imported_runs = RaceRunImportService().import_event_runs(self.event)

        self.assertEqual(imported_runs, 1)
        moto_1 = RaceRun.objects.get(result=self.result, round_type="MOTO", round_number=1)
        self.assertEqual(moto_1.place, "3rd")
        self.assertEqual(moto_1.hill_time, 1.753)
        self.assertIsNone(moto_1.split_1)
        self.assertEqual(moto_1.finish_time, 39.205)

    def test_import_event_runs_parses_final_result_list_times_and_places(self):
        target_dir = os.path.join(settings.MEDIA_ROOT, "event_stats", str(self.event.pk))
        if os.path.isdir(target_dir):
            for filename in os.listdir(target_dir):
                os.remove(os.path.join(target_dir, filename))
        os.makedirs(target_dir, exist_ok=True)

        final_start_html = """<html><body>
        <table class="gridtable">
        <caption>Boys 15-16 (1 Riders)</caption>
        <tr><th>Final</th><th>Lane</th><th>Plate</th><th>Name</th><th>Club</th></tr>
        <tr><td>F1 (A)</td><td>Pick 3</td><td>868</td><td>Simon Aksamit</td><td>Import Club</td></tr>
        </table>
        </body></html>"""
        final_result_html = """<html><body>
        <table class="gridtable">
        <caption>Boys 15-16 (1 Riders)</caption>
        <tr><th>Final</th><th>Result</th><th>Plate</th><th>Club</th><th>Name</th></tr>
        <tr><td>F1 (A)</td><td>1st<br><small>33,380</small></td><td>868</td><td>Import Club</td><td>Simon Aksamit</td></tr>
        </table>
        </body></html>"""

        for filename, content in {
            "final__sample.html": final_start_html,
            "final_results__sample.html": final_result_html,
        }.items():
            with open(os.path.join(target_dir, filename), "w", encoding="utf-8") as handle:
                handle.write(content)

        imported_runs = RaceRunImportService().import_event_runs(self.event)

        self.assertEqual(imported_runs, 1)
        final_run = RaceRun.objects.get(result=self.result, round_type="FINAL")
        self.assertEqual(final_run.heat_code, "F1 (A)")
        self.assertEqual(final_run.lane, 3)
        self.assertEqual(final_run.place, "1st")
        self.assertEqual(final_run.finish_time, 33.380)

    def test_import_event_runs_creates_runs_without_result(self):
        self.result.delete()
        target_dir = os.path.join(settings.MEDIA_ROOT, "event_stats", str(self.event.pk))
        if os.path.isdir(target_dir):
            for filename in os.listdir(target_dir):
                os.remove(os.path.join(target_dir, filename))
        os.makedirs(target_dir, exist_ok=True)

        motos_html = """<html><body>
        <table class="gridtable">
        <caption>Boys 15-16 (1 Riders)</caption>
        <tr><th>Plate</th><th>Club</th><th>Name</th><th>Moto 1</th></tr>
        <tr><td>868</td><td>Import Club</td><td>Simon Aksamit</td><td>40 / 1</td></tr>
        </table>
        </body></html>"""
        motos_results_html = """<html><body>
        <table class="gridtable">
        <caption>Boys 15-16 (1 Riders)</caption>
        <tr><th>Ranking</th><th>Plate</th><th>Club</th><th>Name</th><th>Moto-Points</th><th>Moto 1</th></tr>
        <tr><td>7</td><td>868</td><td>Import Club</td><td>Simon Aksamit</td><td>3</td><td>3rd<br><small>39,205<br>{1.753}</small></td></tr>
        </table>
        </body></html>"""

        for filename, content in {
            "motos__sample.html": motos_html,
            "motos_results__sample.html": motos_results_html,
        }.items():
            with open(os.path.join(target_dir, filename), "w", encoding="utf-8") as handle:
                handle.write(content)

        imported_runs = RaceRunImportService().import_event_runs(self.event)

        self.assertEqual(imported_runs, 1)
        moto_1 = RaceRun.objects.get(event=self.event, rider=self.rider, round_type="MOTO", round_number=1)
        self.assertIsNone(moto_1.result)
        self.assertFalse(moto_1.is_beginner)
        self.assertTrue(moto_1.is_20)
        self.assertEqual(moto_1.finish_time, 39.205)
