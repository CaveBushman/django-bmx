import shutil
import tempfile
from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.core import mail
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
