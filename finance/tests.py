import shutil
import tempfile
from datetime import date, datetime, timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from club.models import Club
from event.credit import calculate_user_balance as calculate_account_balance
from event.models import CreditTransaction, DebetTransaction, Entry, Event, SeasonSettings, StripeFee
from finance.func import calculate_user_balance as calculate_finance_balance
from finance.invoices import delete_invoice_override, save_invoice_override
from finance.models import EventInvoice
from rider.models import Rider, RiderStatsCharge, TrainerClubCharge


User = get_user_model()


class FinanceAccessTests(TestCase):
    def setUp(self):
        self.url = reverse("finance:finance")
        self.admin_user = User.objects.create_user(
            first_name="Finance",
            last_name="Admin",
            username="finance_admin",
            email="finance_admin@example.com",
            password="StrongPass123!",
        )
        self.admin_user.is_active = True
        self.admin_user.is_admin = True
        self.admin_user.save()

    def test_finance_page_redirects_anonymous_user_to_login(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.headers["Location"])

    def test_finance_page_is_available_for_admin_user(self):
        self.client.force_login(self.admin_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)


class FinanceBalanceCalculationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            first_name="Balance",
            last_name="User",
            username="balance_user",
            email="balance_user@example.com",
            password="StrongPass123!",
        )
        self.user.is_active = True
        self.user.save()

        self.club = Club.objects.create(team_name="Balance Club")
        self.season = SeasonSettings.objects.create(year=date.today().year)
        self.period_start = timezone.make_aware(datetime(2026, 1, 1, 0, 0, 0))
        self.period_end = timezone.make_aware(datetime(2026, 1, 31, 0, 0, 0))
        self.rider = Rider.objects.create(
            uci_id=100200301,
            first_name="Balance",
            last_name="Rider",
            date_of_birth=date(2010, 1, 1),
            gender="Muž",
            club=self.club,
            is_active=True,
            is_approved=True,
            is_20=True,
            class_20="Boys 16",
        )

    def test_finance_dashboard_balance_subtracts_registrations_and_premium_charges_only(self):
        CreditTransaction.objects.create(user=self.user, amount=1000, payment_complete=True)
        DebetTransaction.objects.create(user=self.user, amount=200, payment_valid=True)
        RiderStatsCharge.objects.create(
            user=self.user,
            rider=self.rider,
            season=self.season,
            amount=50,
            period_start=self.period_start,
            period_end=self.period_end,
            payment_valid=True,
        )
        TrainerClubCharge.objects.create(
            user=self.user,
            club=self.club,
            season=self.season,
            amount=150,
            period_start=self.period_start,
            period_end=self.period_end,
            payment_valid=True,
        )
        StripeFee.objects.create(date=date.today(), fee=30)

        self.assertEqual(calculate_finance_balance(), 600)

    def test_account_balance_subtracts_trainer_premium_charge(self):
        CreditTransaction.objects.create(user=self.user, amount=1000, payment_complete=True)
        DebetTransaction.objects.create(user=self.user, amount=200, payment_valid=True)
        RiderStatsCharge.objects.create(
            user=self.user,
            rider=self.rider,
            season=self.season,
            amount=50,
            period_start=self.period_start,
            period_end=self.period_end,
            payment_valid=True,
        )
        TrainerClubCharge.objects.create(
            user=self.user,
            club=self.club,
            season=self.season,
            amount=150,
            period_start=self.period_start,
            period_end=self.period_end,
            payment_valid=True,
        )

        self.assertEqual(calculate_account_balance(self.user.id), 600)


class FinanceCreditReportingTests(TestCase):
    def setUp(self):
        self.url = reverse("finance:finance")
        self.admin_user = User.objects.create_user(
            first_name="Finance",
            last_name="Reporter",
            username="finance_reporter",
            email="finance_reporter@example.com",
            password="StrongPass123!",
        )
        self.admin_user.is_active = True
        self.admin_user.is_admin = True
        self.admin_user.save(update_fields=["is_active", "is_admin"])

        self.club = Club.objects.create(team_name="Finance Report Club")
        self.event = Event.objects.create(
            name="Refunded race",
            date=date.today() + timedelta(days=7),
            organizer=self.club,
            type_for_ranking="Volný závod",
        )
        self.rider = Rider.objects.create(
            uci_id=100200399,
            first_name="Refund",
            last_name="Rider",
            date_of_birth=date(2010, 1, 1),
            gender="Muž",
            club=self.club,
            is_active=True,
            is_approved=True,
            is_20=True,
            class_20="Boys 16",
        )
        self.entry = Entry.objects.create(
            user=self.admin_user,
            event=self.event,
            rider=self.rider,
            is_20=True,
            class_20="Boys 16",
            fee_20=350,
            payment_complete=True,
        )
        CreditTransaction.objects.create(
            user=self.admin_user,
            amount=500,
            payment_complete=True,
            payment_intent="pi_topup_123",
            kind=CreditTransaction.Kind.TOPUP,
        )
        CreditTransaction.objects.create(
            user=self.admin_user,
            source_entry=self.entry,
            amount=350,
            payment_complete=True,
            payment_intent=f"Vrácení startovného za závod {self.event.name}",
            kind=CreditTransaction.Kind.CHECKOUT_REFUND,
        )

    @patch("finance.views.SubscriptionInvoiceService.ensure_for_all")
    def test_finance_dashboard_exposes_checkout_refund_summary(self, ensure_for_all_mock):
        self.client.force_login(self.admin_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["credit_transaction_summary"]["topup_total"], 500)
        self.assertEqual(response.context["credit_transaction_summary"]["topup_count"], 1)
        self.assertEqual(response.context["credit_transaction_summary"]["checkout_refund_total"], 350)
        self.assertEqual(response.context["credit_transaction_summary"]["checkout_refund_count"], 1)
        self.assertContains(response, "Checkout refundy")
        self.assertContains(response, "Vrácení startovného po checkoutu")
        ensure_for_all_mock.assert_called_once()

    @patch("finance.views.SubscriptionInvoiceService.ensure_for_all")
    def test_finance_dashboard_lists_only_checkout_refunds_in_detail_table(self, ensure_for_all_mock):
        self.client.force_login(self.admin_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["checkout_refunds"].values_list("kind", flat=True)),
            [CreditTransaction.Kind.CHECKOUT_REFUND],
        )
        self.assertContains(response, f"Vrácení startovného za závod {self.event.name}")
        self.assertNotContains(response, "pi_topup_123")
        self.assertContains(response, "Posledních 100 vratek startovného")
        ensure_for_all_mock.assert_called_once()

    def test_checkout_refund_csv_export_contains_only_refunds(self):
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("finance:export_checkout_refunds_csv"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        content = response.content.decode("utf-8")
        self.assertIn("checkout-refunds.csv", response["Content-Disposition"])
        self.assertIn("Vrácení startovného za závod Refunded race", content)
        self.assertIn("Refund Rider", content)
        self.assertNotIn("pi_topup_123", content)


class CheckoutRefundConsistencyCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            first_name="Consistency",
            last_name="User",
            username="consistency_user",
            email="consistency@example.com",
            password="StrongPass123!",
        )
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])
        self.club = Club.objects.create(team_name="Consistency Club")
        self.event = Event.objects.create(
            name="Consistency Race",
            date=date.today() + timedelta(days=7),
            organizer=self.club,
            type_for_ranking="Volný závod",
        )
        self.rider = Rider.objects.create(
            uci_id=100200400,
            first_name="Consistency",
            last_name="Rider",
            date_of_birth=date(2010, 1, 1),
            gender="Muž",
            club=self.club,
            is_active=True,
            is_approved=True,
            is_20=True,
            class_20="Boys 16",
        )

    def test_report_checkout_refund_consistency_lists_problem_rows(self):
        entry = Entry.objects.create(
            user=self.user,
            event=self.event,
            rider=self.rider,
            is_20=True,
            class_20="Boys 16",
            fee_20=300,
            payment_complete=True,
            checkout=True,
        )
        CreditTransaction.objects.filter(source_entry=entry).delete()
        CreditTransaction.objects.create(
            user=self.user,
            amount=111,
            payment_complete=True,
            payment_intent="orphan refund",
            kind=CreditTransaction.Kind.CHECKOUT_REFUND,
        )

        stdout = StringIO()
        call_command("report_checkout_refund_consistency", stdout=stdout)
        output = stdout.getvalue()

        self.assertIn(f"ENTRY {entry.pk}: checkout=True bez refund transakce", output)
        self.assertIn("orphan refund bez source_entry", output)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EventInvoiceGenerationTests(TestCase):
    def setUp(self):
        self.temp_media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.temp_media)
        self.override.enable()

        self.admin_user = User.objects.create_user(
            first_name="Event",
            last_name="Admin",
            username="event_admin",
            email="event_admin@example.com",
            password="StrongPass123!",
        )
        self.admin_user.is_active = True
        self.admin_user.is_admin = True
        self.admin_user.is_staff = True
        self.admin_user.save()

        self.organizer = Club.objects.create(
            team_name="Organizer Club",
            street="Ulice 1",
            city="Praha",
            zip_code="11000",
            ico="12345678",
            bank_account="123456789/0100",
        )
        self.customer_club = Club.objects.create(
            team_name="Customer Club",
            street="Oddilova 2",
            city="Brno",
            zip_code="60200",
            ico="87654321",
            billing_email="faktury@customer-club.cz",
        )
        self.event = Event.objects.create(
            name="Test Race",
            date=date(2026, 5, 1),
            organizer=self.organizer,
            type_for_ranking="Volný závod",
        )
        self.rider = Rider.objects.create(
            uci_id=100200300,
            first_name="Jan",
            last_name="Novak",
            date_of_birth=date(2010, 1, 1),
            gender="Muž",
            club=self.customer_club,
            is_20=True,
            class_20="Boys 16",
            is_active=True,
            is_approved=True,
        )
        Entry.objects.create(
            event=self.event,
            rider=self.rider,
            is_20=True,
            class_20="Boys 16",
            fee_20=350,
            payment_complete=True,
            checkout=False,
        )

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.temp_media, ignore_errors=True)

    def test_event_admin_generates_invoices_and_sends_email(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("event:event-admin", kwargs={"pk": self.event.pk}),
            {"btn-send-invoices": "invoices"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(EventInvoice.objects.count(), 1)

        invoice = EventInvoice.objects.get()
        self.assertTrue(invoice.pdf.name.startswith("invoices/pdf/"))
        self.assertTrue(invoice.xml_export.name.startswith("invoices/xml/"))
        self.assertEqual(invoice.email_sent_to, "faktury@customer-club.cz")
        self.assertTrue(self.event.__class__.objects.get(pk=self.event.pk).flexibee_export.name.startswith("invoices/xml/"))

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Test Race", mail.outbox[0].subject)

    def test_invoice_override_allows_custom_number_of_lines_and_reset_to_defaults(self):
        self.client.force_login(self.admin_user)
        self.client.post(
            reverse("event:event-admin", kwargs={"pk": self.event.pk}),
            {"btn-send-invoices": "invoices"},
            follow=True,
        )

        save_invoice_override(
            self.event,
            self.customer_club,
            "Ruční položka A\nRuční položka B",
            "100.00\n250.00",
        )

        invoice = EventInvoice.objects.get(event=self.event, club=self.customer_club)
        self.assertEqual(float(invoice.total_price), 350.0)

        invoice.xml_export.open("rb")
        try:
            xml_content = invoice.xml_export.read().decode("utf-8")
        finally:
            invoice.xml_export.close()
        self.assertIn("Ruční položka A", xml_content)
        self.assertIn("Ruční položka B", xml_content)

        delete_invoice_override(self.event, self.customer_club)
        invoice.refresh_from_db()

        invoice.xml_export.open("rb")
        try:
            reset_xml_content = invoice.xml_export.read().decode("utf-8")
        finally:
            invoice.xml_export.close()
        self.assertIn("Jan Novak", reset_xml_content)
