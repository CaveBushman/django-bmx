from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from club.models import Club
from event.models import CreditTransaction, Event, RaceRun, Result, SeasonSettings
from rider.models import Rider, RiderStatsCharge, RiderStatsSubscription


User = get_user_model()


class RiderPremiumSubscriptionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            first_name="Premium",
            last_name="User",
            username="premium_user",
            email="premium@example.com",
            password="StrongPass123!",
        )
        self.user.is_active = True
        self.user.save()

        self.club = Club.objects.create(team_name="Premium Club")
        self.season = SeasonSettings.objects.create(
            year=timezone.now().year,
            rider_stats_monthly_price=50,
        )
        self.rider = Rider.objects.create(
            uci_id=12345670001,
            first_name="Fast",
            last_name="Rider",
            gender="Muž",
            date_of_birth=date(2010, 5, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
        )
        self.event = Event.objects.create(
            name="Premium Race",
            date=date.today() - timedelta(days=7),
            organizer=self.club,
            reg_open=False,
            type_for_ranking="Volný závod",
        )
        self.result = Result.objects.create(
            event=self.event,
            rider=self.rider,
            date=self.event.date,
            event_type=self.event.type_for_ranking,
            organizer=self.club.team_name,
            category=self.rider.class_20,
            place=1,
            points=100,
        )
        self.run = RaceRun.objects.create(
            result=self.result,
            event=self.event,
            rider=self.rider,
            round_type="MOTO",
            round_number=1,
            lane=3,
            finish_time=34.12,
            hill_time=2.56,
            split_1=8.91,
        )

    def test_subscribe_creates_subscription_and_deducts_credit(self):
        CreditTransaction.objects.create(
            user=self.user,
            amount=100,
            transaction_id="credit-1",
            payment_complete=True,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("rider:premium-stats-subscribe", kwargs={"pk": self.rider.uci_id})
        )

        self.assertRedirects(response, reverse("rider:premium-stats", kwargs={"pk": self.rider.uci_id}))
        subscription = RiderStatsSubscription.objects.get(user=self.user, rider=self.rider)
        charge = RiderStatsCharge.objects.get(user=self.user, rider=self.rider)

        self.user.refresh_from_db()
        self.assertEqual(subscription.status, RiderStatsSubscription.STATUS_ACTIVE)
        self.assertTrue(subscription.auto_renew)
        self.assertEqual(subscription.monthly_price, 50)
        self.assertEqual(charge.amount, 50)
        self.assertEqual(self.user.credit, 50)

    def test_premium_stats_requires_subscription(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("rider:premium-stats", kwargs={"pk": self.rider.uci_id}),
            follow=True,
        )

        self.assertRedirects(response, reverse("rider:detail", kwargs={"pk": self.rider.uci_id}))
        self.assertContains(response, "aktivní předplatné")

    def test_premium_stats_page_renders_track_times_for_active_subscription(self):
        CreditTransaction.objects.create(
            user=self.user,
            amount=100,
            transaction_id="credit-2",
            payment_complete=True,
        )
        self.client.force_login(self.user)
        self.client.post(reverse("rider:premium-stats-subscribe", kwargs={"pk": self.rider.uci_id}))

        response = self.client.get(reverse("rider:premium-stats", kwargs={"pk": self.rider.uci_id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "34.12")
        self.assertContains(response, "2.56")
        self.assertContains(response, "8.91")
