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
    cancel_trainer_club_subscription,
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
            is_20=True,
            is_beginner=False,
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
        self.assertContains(response, "34,12")
        self.assertContains(response, "2,56")
        self.assertContains(response, "8,91")

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
            is_20=True,
            is_beginner=False,
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
        self.assertContains(response, "35,44")

    def test_premium_compare_page_renders_hill_and_head_to_head(self):
        CreditTransaction.objects.create(
            user=self.user,
            amount=100,
            transaction_id="credit-4",
            payment_complete=True,
        )
        opponent = Rider.objects.create(
            uci_id=12345670002,
            first_name="Marek",
            last_name="Souper",
            gender="Muž",
            date_of_birth=date(2010, 5, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            class_20=self.rider.class_20,
            is_20=True,
        )
        opponent_result = Result.objects.create(
            event=self.event,
            rider=opponent,
            date=self.event.date,
            event_type=self.event.type_for_ranking,
            organizer=self.club.team_name,
            category=opponent.class_20,
            place=2,
            points=80,
            is_20=True,
        )
        RaceRun.objects.create(
            result=opponent_result,
            event=self.event,
            rider=opponent,
            category=opponent.class_20,
            is_beginner=False,
            is_20=True,
            round_type="MOTO",
            round_number=1,
            heat_code="1",
            lane=4,
            place="2nd",
            finish_time=34.55,
            hill_time=2.61,
        )
        self.client.force_login(self.user)
        self.client.post(reverse("rider:premium-stats-subscribe", kwargs={"pk": self.rider.uci_id}))

        response = self.client.get(
            reverse("rider:premium-compare", kwargs={"pk": self.rider.uci_id}),
            {
                "track": self.club.id,
                "wheel": "20",
                "years": "3",
                "opponent": opponent.uci_id,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Median hill")
        self.assertContains(response, "Porovnání jezdců")
        self.assertContains(response, "Motos")
        self.assertContains(response, "1 : 0")


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

    def test_disabling_last_stats_auto_renew_disables_extended_auto_renew(self):
        stats_subscription, _ = purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )
        extended_subscription, _ = purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_EXTENDED,
        )

        self.assertTrue(extended_subscription.auto_renew)
        cancel_trainer_club_subscription(stats_subscription)
        extended_subscription.refresh_from_db()

        self.assertFalse(extended_subscription.auto_renew)

    def test_extended_expires_when_no_active_stats_remain(self):
        stats_subscription, _ = purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )
        extended_subscription, _ = purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_EXTENDED,
        )

        stats_subscription.expires_at = timezone.now() - timedelta(minutes=1)
        stats_subscription.save(update_fields=["expires_at", "updated"])

        active_extended = get_active_trainer_extended_subscription(self.user)
        extended_subscription.refresh_from_db()

        self.assertIsNone(active_extended)
        self.assertEqual(extended_subscription.status, TrainerClubSubscription.STATUS_EXPIRED)
        self.assertFalse(extended_subscription.auto_renew)


class InactiveRiderActionsTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            first_name="Admin",
            last_name="User",
            username="admin_user",
            email="admin@example.com",
            password="StrongPass123!",
        )
        self.admin_user.is_active = True
        self.admin_user.is_admin = True
        self.admin_user.save()

        self.staff_user = User.objects.create_user(
            first_name="Staff",
            last_name="User",
            username="staff_user",
            email="staff@example.com",
            password="StrongPass123!",
        )
        self.staff_user.is_active = True
        self.staff_user.is_staff = True
        self.staff_user.save()

        self.club = Club.objects.create(team_name="Inactive Club")
        self.other_club = Club.objects.create(team_name="Other Club")
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
        self.club_manager.save()

        self.rider = Rider.objects.create(
            uci_id=12345678901,
            first_name="Inactive",
            last_name="Rider",
            gender="Muž",
            date_of_birth=date(2010, 5, 1),
            club=self.club,
            plate_text="145",
            is_active=True,
            is_approved=True,
            valid_licence=True,
        )
        Rider.objects.filter(pk=self.rider.pk).update(
            created=timezone.now() - timedelta(days=365 * 3)
        )
        self.other_club_rider = Rider.objects.create(
            uci_id=12345678902,
            first_name="Other",
            last_name="Club",
            gender="Muž",
            date_of_birth=date(2010, 5, 1),
            club=self.other_club,
            plate_text="146",
            is_active=True,
            is_approved=True,
            valid_licence=True,
        )
        Rider.objects.filter(pk=self.other_club_rider.pk).update(
            created=timezone.now() - timedelta(days=365 * 3)
        )

    def test_admin_can_deactivate_inactive_rider_from_list(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("rider:inactive-deactivate", kwargs={"rider_id": self.rider.pk}),
            follow=True,
        )

        self.rider.refresh_from_db()
        self.assertRedirects(response, reverse("rider:inactive"))
        self.assertFalse(self.rider.is_active)
        self.assertContains(response, "byl označen jako neaktivní")

    def test_staff_cannot_access_inactive_riders_page(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("rider:inactive"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_club_manager_sees_only_riders_from_own_club(self):
        self.client.force_login(self.club_manager)

        response = self.client.get(reverse("rider:inactive"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.rider.last_name)
        self.assertNotContains(response, self.other_club_rider.last_name)

    def test_club_manager_can_deactivate_only_own_club_rider(self):
        self.client.force_login(self.club_manager)

        own_response = self.client.post(
            reverse("rider:inactive-deactivate", kwargs={"rider_id": self.rider.pk}),
            follow=True,
        )
        self.rider.refresh_from_db()

        blocked_response = self.client.post(
            reverse("rider:inactive-deactivate", kwargs={"rider_id": self.other_club_rider.pk}),
            follow=True,
        )
        self.other_club_rider.refresh_from_db()

        self.assertRedirects(own_response, reverse("rider:inactive"))
        self.assertFalse(self.rider.is_active)
        self.assertTrue(self.other_club_rider.is_active)
        self.assertContains(blocked_response, "nelze deaktivovat")
