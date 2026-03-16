import shutil
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from club.models import Club
from event.models import Entry, Event
from finance.models import EventInvoice
from rider.models import Rider


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
