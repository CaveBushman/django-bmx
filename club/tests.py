import tempfile
from datetime import date
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from club.models import Club, McrClubTeam, McrClubTeamMember
from event.models import Event
from rider.models import Rider


User = get_user_model()


class ClubListTests(TestCase):
    def setUp(self):
        self.matching_club = Club.objects.create(
            team_name="BMX Praha",
            is_active=True,
            region="hlavní město Praha",
            city="Praha",
            contact_person="Jan Novak",
            contact_email="praha@example.com",
        )
        self.other_club = Club.objects.create(
            team_name="BMX Brno",
            is_active=True,
            region="Jihomoravský kraj",
            city="Brno",
            contact_person="Petr Svoboda",
            contact_email="brno@example.com",
        )
        Club.objects.create(
            team_name="Bez klubové příslušnosti",
            is_active=True,
            region="Středočeský kraj",
        )

    def test_club_list_filters_by_search_query(self):
        response = self.client.get(reverse("club:clubs-list"), {"q": "Praha"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "BMX Praha")
        self.assertNotContains(response, "BMX Brno")
        self.assertEqual(response.context["filtered_count"], 1)

    def test_club_list_filters_by_region(self):
        response = self.client.get(
            reverse("club:clubs-list"),
            {"region": "Jihomoravský kraj"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "BMX Brno")
        self.assertNotContains(response, "BMX Praha")
        self.assertEqual(response.context["selected_region"], "Jihomoravský kraj")
        self.assertTrue(response.context["has_active_filters"])


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


class McrClubTeamManagerTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(team_name="MCR Club", is_active=True)
        self.other_club = Club.objects.create(team_name="Other Club", is_active=True)
        self.manager = User.objects.create_user(
            first_name="Club",
            last_name="Manager",
            username="club_manager",
            email="club_manager@example.com",
            password="StrongPass123!",
        )
        self.manager.is_active = True
        self.manager.is_club_manager = True
        self.manager.club = self.club
        self.manager.save(update_fields=["is_active", "is_club_manager", "club"])
        self.regular_user = User.objects.create_user(
            first_name="Regular",
            last_name="User",
            username="regular_user",
            email="regular_user@example.com",
            password="StrongPass123!",
        )
        self.regular_user.is_active = True
        self.regular_user.save(update_fields=["is_active"])
        self.riders = [
            Rider.objects.create(
                uci_id=90000000000 + index,
                first_name=f"Rider{index}",
                last_name="Club",
                date_of_birth=date(2010, 1, index),
                club=self.club,
                gender="Muž",
                is_active=True,
                is_approved=True,
                plate=index,
                class_20="Boys 15",
                class_24="Boys 15 and 16",
            )
            for index in range(1, 6)
        ]
        self.other_rider = Rider.objects.create(
            uci_id=91000000001,
            first_name="Other",
            last_name="Rider",
            date_of_birth=date(2010, 1, 1),
            club=self.other_club,
            gender="Muž",
            is_active=True,
            is_approved=True,
            plate=99,
            class_20="Boys 15",
            class_24="Boys 15 and 16",
        )

    def test_page_requires_club_manager(self):
        self.client.force_login(self.regular_user)

        response = self.client.get(reverse("club:mcr-club-teams", kwargs={"year": 2026}))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_team_form_is_hidden_until_user_starts_create_or_edit(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("club:mcr-club-teams", kwargs={"year": 2026}))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Sestavit družstvo")
        self.assertContains(response, "Nové družstvo")

    def test_new_team_link_shows_team_form(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("club:mcr-club-teams", kwargs={"year": 2026}), {"new": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sestavit družstvo")
        self.assertContains(response, "Rider1 Club #1")

    def test_edit_team_link_shows_team_form(self):
        team = McrClubTeam.objects.create(
            year=2026,
            club=self.club,
            name="Editable Team",
            manager_name="Manager",
            created_by=self.manager,
        )
        self.client.force_login(self.manager)

        response = self.client.get(reverse("club:mcr-club-teams", kwargs={"year": 2026}), {"team": str(team.id)})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Úprava družstva")
        self.assertContains(response, "Editable Team")

    def test_manager_can_create_team_with_same_rider_on_20_and_24(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("club:mcr-club-teams", kwargs={"year": 2026}),
            {
                "name": "A Team",
                "manager_name": "Textový manager",
                "rider_20_1": str(self.riders[0].id),
                "rider_24": str(self.riders[0].id),
                "action": "save",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("club:mcr-club-teams", kwargs={"year": 2026}))
        team = McrClubTeam.objects.get(year=2026, club=self.club, name="A Team")
        self.assertEqual(team.manager_name, "Textový manager")
        self.assertEqual(team.members.count(), 2)
        self.assertEqual(
            set(team.members.values_list("wheel", flat=True)),
            {McrClubTeamMember.WHEEL_20, McrClubTeamMember.WHEEL_24},
        )

    def test_team_rejects_more_than_four_unique_riders(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("club:mcr-club-teams", kwargs={"year": 2026}),
            {
                "name": "Too Big",
                "manager_name": "Manager",
                "rider_20_1": str(self.riders[0].id),
                "rider_20_2": str(self.riders[1].id),
                "rider_20_3": str(self.riders[2].id),
                "rider_20_4": str(self.riders[3].id),
                "rider_24": str(self.riders[4].id),
                "action": "save",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "nejvýše čtyři různé jezdce")
        self.assertFalse(McrClubTeam.objects.filter(name="Too Big").exists())

    def test_team_rejects_rider_from_another_club(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("club:mcr-club-teams", kwargs={"year": 2026}),
            {
                "name": "Other Rider",
                "manager_name": "Manager",
                "rider_20_1": str(self.other_rider.id),
                "action": "save",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(McrClubTeam.objects.filter(name="Other Rider").exists())

    def test_team_rejects_rider_on_same_wheel_in_another_team(self):
        first_team = McrClubTeam.objects.create(
            year=2026,
            club=self.club,
            name="First Team",
            manager_name="Manager",
            created_by=self.manager,
        )
        McrClubTeamMember.objects.create(
            team=first_team,
            rider=self.riders[0],
            wheel=McrClubTeamMember.WHEEL_20,
            position=1,
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("club:mcr-club-teams", kwargs={"year": 2026}),
            {
                "name": "Second Team",
                "manager_name": "Manager",
                "rider_20_1": str(self.riders[0].id),
                "action": "save",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "už je v jiném družstvu přihlášený na 20")
        self.assertFalse(McrClubTeam.objects.filter(name="Second Team").exists())

    def test_team_allows_rider_on_different_wheel_in_another_team(self):
        first_team = McrClubTeam.objects.create(
            year=2026,
            club=self.club,
            name="First Team",
            manager_name="Manager",
            created_by=self.manager,
        )
        McrClubTeamMember.objects.create(
            team=first_team,
            rider=self.riders[0],
            wheel=McrClubTeamMember.WHEEL_20,
            position=1,
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("club:mcr-club-teams", kwargs={"year": 2026}),
            {
                "name": "Second Team",
                "manager_name": "Manager",
                "rider_24": str(self.riders[0].id),
                "action": "save",
            },
        )

        self.assertEqual(response.status_code, 302)
        second_team = McrClubTeam.objects.get(name="Second Team")
        self.assertEqual(second_team.members.get().wheel, McrClubTeamMember.WHEEL_24)

    def test_manager_can_edit_existing_team_without_conflicting_with_itself(self):
        team = McrClubTeam.objects.create(
            year=2026,
            club=self.club,
            name="Editable Team",
            manager_name="Old Manager",
            created_by=self.manager,
        )
        McrClubTeamMember.objects.create(
            team=team,
            rider=self.riders[0],
            wheel=McrClubTeamMember.WHEEL_20,
            position=1,
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("club:mcr-club-teams", kwargs={"year": 2026}),
            {
                "team_id": str(team.id),
                "name": "Editable Team",
                "manager_name": "New Manager",
                "rider_20_1": str(self.riders[0].id),
                "rider_20_2": str(self.riders[1].id),
                "action": "save",
            },
        )

        self.assertEqual(response.status_code, 302)
        team.refresh_from_db()
        self.assertEqual(team.manager_name, "New Manager")
        self.assertEqual(
            set(team.members.values_list("rider_id", "wheel")),
            {
                (self.riders[0].id, McrClubTeamMember.WHEEL_20),
                (self.riders[1].id, McrClubTeamMember.WHEEL_20),
            },
        )

    def test_manager_cannot_edit_team_to_use_same_wheel_rider_from_another_team(self):
        first_team = McrClubTeam.objects.create(
            year=2026,
            club=self.club,
            name="First Team",
            manager_name="Manager",
            created_by=self.manager,
        )
        McrClubTeamMember.objects.create(
            team=first_team,
            rider=self.riders[0],
            wheel=McrClubTeamMember.WHEEL_20,
            position=1,
        )
        edited_team = McrClubTeam.objects.create(
            year=2026,
            club=self.club,
            name="Edited Team",
            manager_name="Manager",
            created_by=self.manager,
        )
        McrClubTeamMember.objects.create(
            team=edited_team,
            rider=self.riders[1],
            wheel=McrClubTeamMember.WHEEL_20,
            position=1,
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("club:mcr-club-teams", kwargs={"year": 2026}),
            {
                "team_id": str(edited_team.id),
                "name": "Edited Team",
                "manager_name": "Manager",
                "rider_20_1": str(self.riders[0].id),
                "action": "save",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "už je v jiném družstvu přihlášený na 20")
        self.assertEqual(
            set(edited_team.members.values_list("rider_id", "wheel")),
            {(self.riders[1].id, McrClubTeamMember.WHEEL_20)},
        )
