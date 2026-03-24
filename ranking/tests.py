from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from club.models import Club
from event.models import Event, Result, SeasonSettings
from ranking.ranking import RankingCount
from rider.models import Rider

User = get_user_model()


class RankingCountTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(team_name="Ranking Club")
        self.season = SeasonSettings.objects.create(
            year=date.today().year,
            best_cup=8,
            best_league=10,
        )
        self.rider = Rider.objects.create(
            uci_id=10125224253,
            first_name="Šimon",
            last_name="Aksamit",
            gender="Muž",
            date_of_birth=date(2009, 8, 2),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            is_20=True,
            class_20="Men Junior",
        )

    def create_result(self, *, days_ago, name, event_type, place, points):
        event_date = date.today() - timedelta(days=days_ago)
        event = Event.objects.create(
            name=name,
            date=event_date,
            organizer=self.club,
            reg_open=False,
            type_for_ranking=event_type,
        )
        return Result.objects.create(
            event=event,
            rider=self.rider,
            date=event_date,
            event_type=event_type,
            organizer=self.club.team_name,
            category=self.rider.class_20,
            place=place,
            points=points,
            is_20=True,
        )

    def test_recount_marks_best_cup_results_by_points_within_last_365_days(self):
        self.create_result(
            days_ago=300,
            name="SAZKA MČR jednotlivců",
            event_type="Mistrovství ČR jednotlivců",
            place=2,
            points=300,
        )

        cup_results = [
            self.create_result(days_ago=346, name="1. závod SAZKA Českého poháru", event_type="Český pohár", place=5, points=90),
            self.create_result(days_ago=345, name="2. závod SAZKA Českého poháru", event_type="Český pohár", place=7, points=75),
            self.create_result(days_ago=324, name="3. závod SAZKA Českého poháru", event_type="Český pohár", place=2, points=130),
            self.create_result(days_ago=323, name="4. závod SAZKA Českého poháru", event_type="Český pohár", place=3, points=115),
            self.create_result(days_ago=310, name="5. závod SAZKA Českého poháru", event_type="Český pohár", place=7, points=75),
            self.create_result(days_ago=309, name="6. závod SAZKA Českého poháru", event_type="Český pohár", place=4, points=100),
            self.create_result(days_ago=191, name="7. závod SAZKA Českého poháru", event_type="Český pohár", place=1, points=150),
            self.create_result(days_ago=190, name="8. závod SAZKA Českého poháru", event_type="Český pohár", place=2, points=130),
            self.create_result(days_ago=177, name="9. závod SAZKA Českého poháru", event_type="Český pohár", place=2, points=130),
            self.create_result(days_ago=176, name="10. závod SAZKA Českého poháru", event_type="Český pohár", place=8, points=70),
        ]

        league_results = [
            self.create_result(days_ago=206, name="6. závod České ligy", event_type="Česká liga", place=2, points=70),
            self.create_result(days_ago=199, name="7. závod České ligy", event_type="Česká liga", place=7, points=25),
            self.create_result(days_ago=179, name="8. závod České ligy", event_type="Česká liga", place=1, points=90),
            self.create_result(days_ago=178, name="9. závod České ligy", event_type="Česká liga", place=1, points=90),
            self.create_result(days_ago=165, name="Velká cena Prahy 8", event_type="Volný závod", place=1, points=90),
            self.create_result(days_ago=164, name="Bohnická Fašírka", event_type="Volný závod", place=1, points=90),
            self.create_result(days_ago=144, name="ŽENDA RACE 2025", event_type="Volný závod", place=1, points=90),
        ]

        old_cup = self.create_result(
            days_ago=366,
            name="Historický závod SAZKA Českého poháru",
            event_type="Český pohár",
            place=1,
            points=150,
        )
        old_cup.marked_20 = True
        old_cup.save(update_fields=["marked_20"])

        RankingCount.set_ranking_points()

        selected_cup_ids = set(
            Result.objects.filter(
                rider=self.rider,
                event_type="Český pohár",
                marked_20=True,
            ).values_list("id", flat=True)
        )
        expected_cup_ids = {result.id for result in cup_results if result.points >= 75}

        self.assertSetEqual(selected_cup_ids, expected_cup_ids)
        self.assertIn(cup_results[5].id, selected_cup_ids)
        self.assertNotIn(cup_results[9].id, selected_cup_ids)
        self.assertFalse(Result.objects.get(id=old_cup.id).marked_20)

        self.rider.refresh_from_db()
        expected_total = 300 + sum(result.points for result in cup_results if result.points >= 75) + sum(result.points for result in league_results)
        self.assertEqual(self.rider.points_20, expected_total)


class RankingRecountViewTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(team_name="Ranking Club")
        SeasonSettings.objects.create(
            year=date.today().year,
            best_cup=1,
            best_league=0,
        )
        self.staff_user = User.objects.create_user(
            first_name="Admin",
            last_name="User",
            username="ranking_admin",
            email="ranking_admin@example.com",
            password="StrongPass123!",
        )
        self.staff_user.is_staff = True
        self.staff_user.is_active = True
        self.staff_user.save(update_fields=["is_staff", "is_active"])

        self.rider = Rider.objects.create(
            uci_id=12345678901,
            first_name="View",
            last_name="Tester",
            gender="Muž",
            date_of_birth=date(2009, 8, 2),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            is_20=True,
            class_20="Men Junior",
        )

    @patch("rider.views.schedule_ranking_recount")
    def test_staff_recount_view_schedules_background_recount(self, schedule_mock):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("rider:ranking"), follow=True)

        self.assertRedirects(response, reverse("rider:admin"))
        schedule_mock.assert_called_once_with()
        self.assertContains(response, "Přepočet rankingu byl spuštěn na pozadí")
