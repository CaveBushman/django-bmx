from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from club.models import Club
from event.models import CreditTransaction, Event, RaceRun, Result, SeasonSettings
from rider.models import (
    Rider,
    RiderStatsCharge,
    RiderStatsSubscription,
    TrainerClubCharge,
    TrainerClubSubscription,
)
from rider.subscriptions import (
    get_active_trainer_extended_subscription,
    has_active_trainer_club_extended_access,
    has_active_trainer_club_stats_access,
    purchase_trainer_club_subscription,
)


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

    def test_staff_can_access_premium_stats_without_subscription(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.client.force_login(self.user)

        response = self.client.get(reverse("rider:premium-stats", kwargs={"pk": self.rider.uci_id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Administrátorský přístup")

    def test_premium_stats_supports_track_selection(self):
        CreditTransaction.objects.create(
            user=self.user,
            amount=100,
            transaction_id="credit-3",
            payment_complete=True,
        )
        other_club = Club.objects.create(team_name="Secondary Track")
        other_event = Event.objects.create(
            name="Secondary Race",
            date=date.today() - timedelta(days=3),
            organizer=other_club,
            reg_open=False,
            type_for_ranking="Volný závod",
        )
        other_result = Result.objects.create(
            event=other_event,
            rider=self.rider,
            date=other_event.date,
            event_type=other_event.type_for_ranking,
            organizer=other_club.team_name,
            category=self.rider.class_20,
            place=4,
            points=50,
        )
        RaceRun.objects.create(
            result=other_result,
            event=other_event,
            rider=self.rider,
            round_type="FINAL",
            lane=5,
            place="4th",
            finish_time=35.44,
        )

        self.client.force_login(self.user)
        self.client.post(reverse("rider:premium-stats-subscribe", kwargs={"pk": self.rider.uci_id}))

        response = self.client.get(
            reverse("rider:premium-stats", kwargs={"pk": self.rider.uci_id}),
            {"track": other_club.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Secondary Track")
        self.assertContains(response, "Traťový profil")
        self.assertContains(response, "35.44")


class TrainerClubSubscriptionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            first_name="Coach",
            last_name="User",
            username="coach_user",
            email="coach@example.com",
            password="StrongPass123!",
        )
        self.user.is_active = True
        self.user.is_trainer = True
        self.club = Club.objects.create(team_name="Coach Club")
        self.other_club = Club.objects.create(team_name="Second Club")
        self.user.save()
        self.user.trainer_clubs.add(self.club, self.other_club)

        self.season = SeasonSettings.objects.create(
            year=timezone.now().year,
            rider_stats_monthly_price=50,
            trainer_club_stats_monthly_price=300,
            trainer_extended_monthly_price=600,
        )
        CreditTransaction.objects.create(
            user=self.user,
            amount=2000,
            transaction_id="coach-credit",
            payment_complete=True,
        )

    def test_purchase_trainer_club_stats_subscription_is_billed_per_club(self):
        subscription, created = purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )

        self.assertTrue(created)
        self.user.refresh_from_db()
        self.assertEqual(subscription.club, self.club)
        self.assertEqual(subscription.product, TrainerClubSubscription.PRODUCT_CLUB_STATS)
        self.assertEqual(subscription.monthly_price, 300)
        self.assertTrue(
            TrainerClubCharge.objects.filter(
                user=self.user,
                club=self.club,
                product=TrainerClubSubscription.PRODUCT_CLUB_STATS,
                amount=300,
            ).exists()
        )
        self.assertTrue(has_active_trainer_club_stats_access(self.user, self.club))
        self.assertFalse(has_active_trainer_club_extended_access(self.user, self.club))

    def test_purchase_extended_trainer_subscription_is_global_for_all_stats_clubs(self):
        purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )
        purchase_trainer_club_subscription(
            self.user,
            self.other_club,
            TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )
        subscription, created = purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_EXTENDED,
        )

        self.assertTrue(created)
        self.user.refresh_from_db()
        self.assertEqual(subscription.product, TrainerClubSubscription.PRODUCT_EXTENDED)
        self.assertEqual(subscription.monthly_price, 600)
        self.assertEqual(
            TrainerClubSubscription.objects.filter(
                user=self.user,
                product=TrainerClubSubscription.PRODUCT_EXTENDED,
            ).count(),
            1,
        )
        self.assertIsNotNone(get_active_trainer_extended_subscription(self.user))
        self.assertTrue(has_active_trainer_club_stats_access(self.user, self.club))
        self.assertTrue(has_active_trainer_club_extended_access(self.user, self.club))
        self.assertTrue(has_active_trainer_club_extended_access(self.user, self.other_club))

    def test_extended_requires_active_stats_on_club(self):
        purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )
        purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_EXTENDED,
        )

        self.assertTrue(has_active_trainer_club_extended_access(self.user, self.club))
        self.assertFalse(has_active_trainer_club_extended_access(self.user, self.other_club))

    def test_trainer_stats_subscriptions_remain_separate_for_each_club(self):
        purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )
        purchase_trainer_club_subscription(
            self.user,
            self.other_club,
            TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )

        self.assertEqual(
            TrainerClubSubscription.objects.filter(
                user=self.user,
                product=TrainerClubSubscription.PRODUCT_CLUB_STATS,
            ).count(),
            2,
        )

    def test_extended_cannot_be_purchased_without_any_stats_subscription(self):
        with self.assertRaisesMessage(ValueError, "alespoň jednoho klubu"):
            purchase_trainer_club_subscription(
                self.user,
                self.club,
                TrainerClubSubscription.PRODUCT_EXTENDED,
            )
