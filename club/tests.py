import tempfile
from datetime import date
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from club.models import Club
from event.models import Event
from rider.models import Rider


User = get_user_model()


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ClubExportTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(team_name="Club Export Team", is_active=True)
        self.staff_user = User.objects.create_user(
            first_name="Club",
            last_name="Staff",
            username="club_staff",
            email="club_staff@example.com",
            password="StrongPass123!",
        )
        self.staff_user.is_staff = True
        self.staff_user.is_active = True
        self.staff_user.save(update_fields=["is_staff", "is_active"])

        self.regular_user = User.objects.create_user(
            first_name="Club",
            last_name="User",
            username="club_user",
            email="club_user@example.com",
            password="StrongPass123!",
        )
        self.regular_user.is_active = True
        self.regular_user.save(update_fields=["is_active"])

        Rider.objects.create(
            uci_id=12345678901,
            first_name="Alice",
            last_name="Rider",
            date_of_birth=date(2010, 1, 1),
            club=self.club,
            gender="Žena",
            is_active=True,
            is_approved=True,
            plate=12,
            class_20="Girls 15",
            class_24="Women 17-24",
        )

        Event.objects.create(
            name="Club Export Race",
            date=date(date.today().year, 6, 1),
            organizer=self.club,
            type_for_ranking="Volný závod",
            reg_open=False,
        )

    def test_riders_on_events_export_requires_staff_login(self):
        response = self.client.get(
            reverse("club:riders-on-events-export", kwargs={"pk": self.club.id})
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/bmx-admin/login/", response["Location"])

    def test_riders_on_events_export_returns_xlsx_for_staff(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(
            reverse("club:riders-on-events-export", kwargs={"pk": self.club.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("RIDERS_IN_EVENTS-", response["Content-Disposition"])

    def test_club_export_view_source_does_not_use_direct_file_open(self):
        source = (
            Path(__file__).resolve().parent / "views.py"
        ).read_text(encoding="utf-8")

        self.assertIn("storage", source)
        self.assertNotIn("open(file_path, \"rb\")", source)
