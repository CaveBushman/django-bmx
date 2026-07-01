from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from club.models import Club
from event.models import Event, Result, SeasonSettings
from ranking.ranking import RankingCount, RANKING_RECOUNT_STATUS_KEY, get_ranking_recount_status
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
        expected_cup_ids = {
            result.id for result in sorted(cup_results, key=lambda result: (-result.points, -result.date.toordinal()))[:8]
        }

        self.assertSetEqual(selected_cup_ids, expected_cup_ids)
        self.assertIn(cup_results[5].id, selected_cup_ids)
        self.assertNotIn(cup_results[9].id, selected_cup_ids)
        self.assertFalse(Result.objects.get(id=old_cup.id).marked_20)

        self.rider.refresh_from_db()
        expected_total = (
            300
            + sum(
                result.points
                for result in sorted(cup_results, key=lambda result: (-result.points, -result.date.toordinal()))[:8]
            )
            + sum(result.points for result in league_results)
        )
        self.assertEqual(self.rider.points_20, expected_total)

    def test_recount_ignores_zero_point_results_when_selecting_counted_races(self):
        SeasonSettings.objects.filter(pk=self.season.pk).update(best_cup=0, best_league=1)

        zero_points_result = self.create_result(
            days_ago=20,
            name="Nebodovaný start",
            event_type="Volný závod",
            place=15,
            points=0,
        )
        counted_result = self.create_result(
            days_ago=10,
            name="Bodovaný start",
            event_type="Volný závod",
            place=4,
            points=55,
        )

        RankingCount.set_ranking_points()

        zero_points_result.refresh_from_db()
        counted_result.refresh_from_db()
        self.rider.refresh_from_db()

        self.assertFalse(zero_points_result.marked_20)
        self.assertTrue(counted_result.marked_20)
        self.assertEqual(self.rider.points_20, 55)

    def test_recount_clears_stale_mark_on_zero_point_result(self):
        SeasonSettings.objects.filter(pk=self.season.pk).update(best_cup=0, best_league=1)

        stale_zero_points_result = self.create_result(
            days_ago=20,
            name="Open Season 2026",
            event_type="Volný závod",
            place=21,
            points=0,
        )
        stale_zero_points_result.marked_20 = True
        stale_zero_points_result.save(update_fields=["marked_20"])

        counted_result = self.create_result(
            days_ago=10,
            name="Bodovaný start",
            event_type="Volný závod",
            place=4,
            points=55,
        )

        RankingCount.set_ranking_points()

        stale_zero_points_result.refresh_from_db()
        counted_result.refresh_from_db()
        self.rider.refresh_from_db()

        self.assertFalse(stale_zero_points_result.marked_20)
        self.assertTrue(counted_result.marked_20)
        self.assertEqual(self.rider.points_20, 55)


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

    @patch("rider.views.admin.schedule_ranking_recount")
    def test_staff_recount_view_schedules_background_recount(self, schedule_mock):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("rider:ranking"), follow=True)

        self.assertRedirects(response, reverse("rider:admin"))
        schedule_mock.assert_called_once_with()
        self.assertContains(response, "Přepočet rankingu byl spuštěn na pozadí")


class RankingViewTemplateTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(team_name="Ranking View Club")
        self.rider = Rider.objects.create(
            uci_id=12345678910,
            first_name="Alice",
            last_name="Leader",
            gender="Žena",
            date_of_birth=date(2008, 6, 15),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            is_20=True,
            class_20="Women 17-24",
            points_20=120,
            ranking_20="1",
        )

    def test_ranking_view_renders_card_layout(self):
        response = self.client.get(reverse("ranking:ranking"), {"category": "Women 17-24"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ranking-card")
        self.assertContains(response, "LEADER")
        self.assertContains(response, "Alice")
        self.assertContains(response, "120 b.")
        self.assertContains(response, 'option value="Women 17-24" selected')

    def test_ranking_view_shows_notice_for_invalid_category(self):
        response = self.client.get(reverse("ranking:ranking"), {"category": "Unknown Category"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Požadovaná kategorie v URL nebyla nalezena")


class RankingRecountStatusTests(TestCase):
    def test_status_reader_exposes_cached_metadata(self):
        started_at = timezone.now()
        finished_at = timezone.now()
        cache.set(
            RANKING_RECOUNT_STATUS_KEY,
            {
                "last_started_at": started_at,
                "last_finished_at": finished_at,
                "last_duration_seconds": 1.25,
                "last_success": True,
                "last_message": "Poslední přepočet rankingu doběhl úspěšně.",
                "last_rider_count": 12,
            },
        )

        status = get_ranking_recount_status()

        self.assertEqual(status["last_started_at"], started_at)
        self.assertEqual(status["last_finished_at"], finished_at)
        self.assertEqual(status["last_duration_seconds"], 1.25)
        self.assertTrue(status["last_success"])
        self.assertEqual(status["last_rider_count"], 12)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class RecountDispatchTests(TestCase):
    """Ověřuje volbu mezi Celery taskem a vláknem podle should_use_celery().
    Cache je přepnutá na LocMem, aby test nezávisel na běžícím Redisu."""

    def setUp(self):
        cache.clear()

    @patch("ranking.ranking.transaction.on_commit", side_effect=lambda fn: fn())
    @patch("bmx.background.should_use_celery", return_value=True)
    def test_ranking_recount_dispatches_celery_when_broker_available(self, _celery, _commit):
        from ranking.ranking import schedule_ranking_recount

        with patch("ranking.tasks.recount_ranking_task.delay") as delay_mock:
            with patch("ranking.ranking.SetRanking") as thread_mock:
                schedule_ranking_recount()

        delay_mock.assert_called_once()
        thread_mock.assert_not_called()

    @patch("ranking.ranking.transaction.on_commit", side_effect=lambda fn: fn())
    @patch("bmx.background.should_use_celery", return_value=False)
    def test_ranking_recount_falls_back_to_thread_without_broker(self, _celery, _commit):
        from ranking.ranking import schedule_ranking_recount

        with patch("ranking.tasks.recount_ranking_task.delay") as delay_mock:
            with patch("ranking.ranking.SetRanking") as thread_mock:
                schedule_ranking_recount()

        thread_mock.assert_called_once()
        delay_mock.assert_not_called()

    @patch("bmx.background.should_use_celery", return_value=True)
    def test_cn_qualification_dispatches_celery(self, _celery):
        from rider.rider import start_cn_qualification_recount

        with patch("rider.tasks.recount_cn_qualification_task.delay") as delay_mock:
            with patch("rider.rider.RiderQualifyToCNThread") as thread_mock:
                start_cn_qualification_recount(year=2026)

        delay_mock.assert_called_once_with(2026)
        thread_mock.assert_not_called()

    @patch("bmx.background.should_use_celery", return_value=False)
    def test_cn_qualification_falls_back_to_thread(self, _celery):
        from rider.rider import start_cn_qualification_recount

        with patch("rider.tasks.recount_cn_qualification_task.delay") as delay_mock:
            with patch("rider.rider.RiderQualifyToCNThread") as thread_mock:
                start_cn_qualification_recount(year=2026)

        thread_mock.assert_called_once_with(year=2026)
        delay_mock.assert_not_called()
