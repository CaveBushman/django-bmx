import base64
import uuid
from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from io import BytesIO
from PIL import Image
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from types import SimpleNamespace
from unittest.mock import patch

from club.models import Club
from event.models import CreditTransaction, Entry, Event, Result, SeasonSettings
from news.models import News
from rider.models import (
    MobileAppSubscription,
    PromoCode,
    PromoCodeUsage,
    Rider,
    RiderTransponderChange,
)

User = get_user_model()


def make_user(**kwargs):
    defaults = dict(
        first_name="Test",
        last_name="User",
        username=kwargs.pop("username", "testuser"),
        email=kwargs.pop("email", "test@example.com"),
        password="StrongPass123!",
    )
    defaults.update(kwargs)
    user = User.objects.create_user(**defaults)
    user.is_active = True
    user.save(update_fields=["is_active"])
    return user


class PlateRequestLookupAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/v1/riders/plate-request/lookup/"

    @patch("api.views.plates.get_rider_data", return_value=(None, "Nastala chyba: 500"))
    def test_lookup_cannot_continue_without_personal_details(self, _get_rider_data):
        response = self.client.get(self.url, {"uci_id": "10046761357"})

        self.assertEqual(response.status_code, 502)
        self.assertIn("Údaje licence", response.data["error"])


class LoginAPITests(TestCase):
    def setUp(self):
        cache.clear()  # reset login rate-limit bucket (sdílený throttle scope mezi testy)
        self.client = APIClient()
        self.user = make_user()
        self.url = "/api/v1/auth/login/"

    def test_login_returns_access_and_refresh_tokens(self):
        response = self.client.post(self.url, {"email": "test@example.com", "password": "StrongPass123!"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertIn("user", response.data)

    def test_login_user_payload_contains_required_fields(self):
        response = self.client.post(self.url, {"email": "test@example.com", "password": "StrongPass123!"})
        user_data = response.data["user"]
        for field in ("id", "email", "first_name", "last_name", "credit", "is_staff", "is_rider"):
            self.assertIn(field, user_data, msg=f"Missing field: {field}")

    def test_login_wrong_password_returns_401(self):
        response = self.client.post(self.url, {"email": "test@example.com", "password": "wrong"})
        self.assertEqual(response.status_code, 401)

    def test_login_missing_fields_returns_400(self):
        response = self.client.post(self.url, {"email": "test@example.com"})
        self.assertEqual(response.status_code, 400)

    def test_login_inactive_user_returns_403(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post(self.url, {"email": "test@example.com", "password": "StrongPass123!"})
        self.assertEqual(response.status_code, 403)


class TokenRefreshTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user(username="refresh_user", email="refresh@example.com")

    def test_refresh_returns_new_access_token(self):
        refresh = RefreshToken.for_user(self.user)
        response = self.client.post("/api/v1/auth/token/refresh/", {"refresh": str(refresh)})
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    def test_invalid_refresh_token_returns_401(self):
        response = self.client.post("/api/v1/auth/token/refresh/", {"refresh": "invalid.token.here"})
        self.assertEqual(response.status_code, 401)


class LogoutAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user(username="logout_user", email="logout@example.com")

    def _auth(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        return str(refresh)

    def test_logout_with_refresh_token_returns_204(self):
        refresh_str = self._auth()
        response = self.client.post("/api/v1/auth/logout/", {"refresh": refresh_str})
        self.assertEqual(response.status_code, 204)

    def test_logout_blacklists_refresh_token(self):
        refresh_str = self._auth()
        self.client.post("/api/v1/auth/logout/", {"refresh": refresh_str})
        response = self.client.post("/api/v1/auth/token/refresh/", {"refresh": refresh_str})
        self.assertEqual(response.status_code, 401)

    def test_unauthenticated_logout_returns_401(self):
        response = self.client.post("/api/v1/auth/logout/")
        self.assertEqual(response.status_code, 401)


class MeAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user(username="me_user", email="me@example.com")
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    def test_get_me_returns_user_data(self):
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], "me@example.com")

    def test_patch_me_updates_name(self):
        response = self.client.patch("/api/v1/auth/me/", {"first_name": "Nové", "last_name": "Jméno"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["first_name"], "Nové")
        self.assertEqual(response.data["last_name"], "Jméno")

    def test_patch_me_ignores_disallowed_fields(self):
        original_email = self.user.email
        response = self.client.patch("/api/v1/auth/me/", {"email": "hacker@evil.com"})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, original_email)

    @override_settings(MEDIA_ROOT="/tmp/czechbmx-api-test-media")
    def test_patch_me_updates_photo(self):
        image = BytesIO()
        Image.new("RGB", (240, 240), color=(20, 80, 160)).save(image, format="JPEG")
        image.seek(0)
        upload = SimpleUploadedFile(
            "avatar.jpg",
            image.read(),
            content_type="image/jpeg",
        )

        response = self.client.patch(
            "/api/v1/auth/me/",
            {"photo": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["photo_url"])
        self.user.refresh_from_db()
        self.assertIn("images/users/", self.user.photo.name)
        self.assertTrue(
            self.user.photo.name.endswith(".webp")
            or self.user.photo.name.endswith(".jpg")
        )

    def test_unauthenticated_me_returns_401(self):
        self.client.credentials()
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 401)


class CreditTopUpAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user(username="credit_user", email="credit@example.com")
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    @patch("api.views.auth.stripe.checkout.Session.create")
    def test_credit_topup_creates_stripe_checkout_session(self, create_mock):
        create_mock.return_value = SimpleNamespace(
            id="cs_test_mobile_credit",
            url="https://checkout.stripe.com/c/pay/cs_test_mobile_credit",
        )

        response = self.client.post("/api/v1/credit/topup/", {"amount": 500})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data["checkout_url"],
            "https://checkout.stripe.com/c/pay/cs_test_mobile_credit",
        )
        transaction = CreditTransaction.objects.get(transaction_id="cs_test_mobile_credit")
        self.assertEqual(transaction.user, self.user)
        self.assertEqual(transaction.amount, 500)
        self.assertEqual(transaction.kind, CreditTransaction.Kind.TOPUP)
        self.assertFalse(transaction.payment_complete)
        create_mock.assert_called_once()

    def test_credit_topup_rejects_low_amount(self):
        response = self.client.post("/api/v1/credit/topup/", {"amount": 99})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(CreditTransaction.objects.exists())

    def test_credit_topup_requires_authentication(self):
        self.client.credentials()
        response = self.client.post("/api/v1/credit/topup/", {"amount": 500})
        self.assertEqual(response.status_code, 401)


class PasswordChangeAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user(username="pwd_user", email="pwd@example.com")
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    def test_password_change_success(self):
        response = self.client.post(
            "/api/v1/auth/password/change/",
            {"old_password": "StrongPass123!", "new_password": "NewPass456!"},
        )
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPass456!"))

    def test_wrong_old_password_returns_400(self):
        response = self.client.post(
            "/api/v1/auth/password/change/",
            {"old_password": "wrong", "new_password": "NewPass456!"},
        )
        self.assertEqual(response.status_code, 400)

    def test_short_new_password_returns_400(self):
        response = self.client.post(
            "/api/v1/auth/password/change/",
            {"old_password": "StrongPass123!", "new_password": "short"},
        )
        self.assertEqual(response.status_code, 400)


class RiderListAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user(username="rider_api_user", email="rider_api@example.com")
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    def test_rider_list_is_public(self):
        self.client.credentials()
        response = self.client.get("/api/v1/riders/")
        self.assertEqual(response.status_code, 200)

    def test_authenticated_user_can_access_rider_list(self):
        response = self.client.get("/api/v1/riders/")
        self.assertEqual(response.status_code, 200)

    def test_response_is_paginated(self):
        response = self.client.get("/api/v1/riders/")
        self.assertIn("count", response.data)
        self.assertIn("results", response.data)


class NewsListAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_news_list_returns_only_articles_published_in_app(self):
        visible = News.objects.create(
            title="Visible article",
            perex="prefix",
            content="content",
            published=True,
            publish_in_app=True,
        )
        News.objects.create(
            title="Hidden article",
            perex="prefix",
            content="content",
            published=True,
            publish_in_app=False,
        )

        response = self.client.get("/api/v1/news/")

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        self.assertEqual([item["id"] for item in response.data], [visible.id])

    def test_news_list_is_not_paginated_and_orders_by_publish_date_desc(self):
        older = News.objects.create(
            title="Older article",
            perex="prefix",
            content="content",
            published=True,
            publish_in_app=True,
            publish_date=date(2026, 7, 20),
        )
        newer = News.objects.create(
            title="Newer article",
            perex="prefix",
            content="content",
            published=True,
            publish_in_app=True,
            publish_date=date(2026, 7, 21),
        )

        # Opačné pořadí created_date hlídá, že API skutečně používá publish_date.
        News.objects.filter(pk=older.pk).update(created_date=timezone.now())
        News.objects.filter(pk=newer.pk).update(created_date=timezone.now() - timedelta(days=1))

        response = self.client.get("/api/v1/news/")

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        self.assertEqual([item["id"] for item in response.data[:2]], [newer.id, older.id])


class ResultFeedAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.club = Club.objects.create(team_name="BMX Praha")
        self.other_club = Club.objects.create(team_name="BMX Brno")
        self.event = Event.objects.create(
            name="Český pohár Praha",
            date=date(2026, 5, 10),
            organizer=self.club,
            type_for_ranking="Český pohár",
        )
        self.other_event = Event.objects.create(
            name="Volný závod Brno",
            date=date(2025, 6, 1),
            organizer=self.other_club,
            type_for_ranking="Volný závod",
        )
        self.rider = Rider.objects.create(
            uci_id=100000001,
            first_name="Adam",
            last_name="Novák",
            gender="Muž",
            date_of_birth=date(2012, 1, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            class_20="Boys 14",
        )
        self.other_rider = Rider.objects.create(
            uci_id=100000002,
            first_name="Eva",
            last_name="Svobodová",
            gender="Žena",
            date_of_birth=date(2011, 1, 1),
            club=self.other_club,
            is_active=True,
            is_approved=True,
            class_24="Girls 13-16",
        )
        self.result = Result.objects.create(
            event=self.event,
            date=self.event.date,
            event_type=self.event.type_for_ranking,
            organizer=self.club.team_name,
            rider=self.rider,
            first_name=self.rider.first_name,
            last_name=self.rider.last_name,
            club=self.club.team_name,
            country="CZE",
            category="Boys 14",
            place=1,
            points=100,
            is_20=True,
            marked_20=True,
        )
        self.cruiser_result = Result.objects.create(
            event=self.other_event,
            date=self.other_event.date,
            event_type=self.other_event.type_for_ranking,
            organizer=self.other_club.team_name,
            rider=self.other_rider,
            first_name=self.other_rider.first_name,
            last_name=self.other_rider.last_name,
            club=self.other_club.team_name,
            country="CZE",
            category="Girls 13-16 Cruiser",
            place=2,
            points=80,
            is_20=False,
            marked_24=True,
        )

    def test_v1_results_returns_paginated_feed(self):
        response = self.client.get("/api/v1/results/feed/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        item = response.data["results"][0]
        self.assertIn("event_name", item)
        self.assertIn("type_for_ranking", item)
        self.assertIn("rider_uci_id", item)
        self.assertIn("wheel", item)

    def test_v1_results_filters_by_year_event_type_and_wheel(self):
        response = self.client.get(
            "/api/v1/results/feed/",
            {"year": "2026", "event_type": "Český pohár", "is_20": "true"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.result.id)
        self.assertEqual(response.data["results"][0]["wheel"], "20")

    def test_v1_results_filters_cruiser_by_is_24(self):
        response = self.client.get("/api/v1/results/feed/", {"is_24": "true"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.cruiser_result.id)
        self.assertEqual(response.data["results"][0]["wheel"], "24")

    def test_v1_event_results_limits_results_to_event(self):
        response = self.client.get(f"/api/v1/events/{self.event.id}/results/feed/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["event"], self.event.id)


# ===========================================================================
# Helpers shared by new API test classes
# ===========================================================================

def _make_credited_user(username, *, credit=0, is_staff=False, is_superuser=False):
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="StrongPass123!",
        first_name="Test",
        last_name="User",
    )
    user.is_active = True
    user.is_staff = is_staff
    user.is_superuser = is_superuser
    user.save()
    if credit > 0:
        CreditTransaction.objects.create(
            user=user,
            amount=credit,
            transaction_id=f"tx-api-{username}",
            payment_complete=True,
        )
        user.credit = credit
        user.save(update_fields=["credit"])
    return user


def _make_season(price=499):
    season, _ = SeasonSettings.objects.get_or_create(
        year=timezone.now().year,
        defaults={"mobile_app_annual_price": price},
    )
    season.mobile_app_annual_price = price
    season.save(update_fields=["mobile_app_annual_price"])
    return season


def _make_promo(*, discount_type=PromoCode.DISCOUNT_FREE, discount_value=100,
                product=PromoCode.PRODUCT_MOBILE_APP, max_uses=None,
                is_active=True, valid_until=None):
    return PromoCode.objects.create(
        discount_type=discount_type,
        discount_value=discount_value,
        product=product,
        max_uses=max_uses,
        is_active=is_active,
        valid_until=valid_until,
    )


def _auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


# ===========================================================================
# GlobalSearchAPIView — GET /api/v1/search/
# ===========================================================================

class GlobalSearchAPITests(TestCase):
    def setUp(self):
        self.user = make_user(username="search_user", email="search@example.com")
        self.client = _auth_client(self.user)

        club = Club.objects.create(team_name="Search Club")
        self.rider = Rider.objects.create(
            uci_id=99900001,
            first_name="Novák",
            last_name="Testovací",
            date_of_birth=date(2005, 1, 1),
            is_active=True,
            is_approved=True,
            club=club,
        )
        self.event = Event.objects.create(
            name="Pohár Novák Open",
            date=date(2026, 7, 1),
            type_for_ranking="Český pohár",
        )
        self.news = News.objects.create(
            title="Novák wins race",
            slug="novak-wins-race",
            perex="Test perex",
            published=True,
            publish_in_app=True,
        )

    def test_short_query_returns_empty(self):
        response = self.client.get("/api/v1/search/", {"q": "N"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["riders"], [])
        self.assertEqual(response.data["events"], [])
        self.assertEqual(response.data["news"], [])

    def test_query_finds_rider_by_last_name(self):
        response = self.client.get("/api/v1/search/", {"q": "Novák"})
        self.assertEqual(response.status_code, 200)
        uci_ids = [r["uci_id"] for r in response.data["riders"]]
        self.assertIn(self.rider.uci_id, uci_ids)

    def test_query_finds_event_by_name(self):
        response = self.client.get("/api/v1/search/", {"q": "Pohár"})
        self.assertEqual(response.status_code, 200)
        event_ids = [e["id"] for e in response.data["events"]]
        self.assertIn(self.event.id, event_ids)

    def test_query_finds_news_by_title(self):
        response = self.client.get("/api/v1/search/", {"q": "Novák wins"})
        self.assertEqual(response.status_code, 200)
        news_titles = [n["title"] for n in response.data["news"]]
        self.assertIn("Novák wins race", news_titles)

    def test_news_results_are_ordered_by_publish_date_desc(self):
        older_by_publish_date = News.objects.create(
            title="Novák older publication",
            slug="novak-older-publication",
            perex="Test perex",
            published=True,
            publish_date=date(2026, 7, 19),
        )
        News.objects.filter(pk=older_by_publish_date.pk).update(created_date=timezone.now())
        News.objects.filter(pk=self.news.pk).update(
            created_date=timezone.now() - timedelta(days=1),
            publish_date=date(2026, 7, 20),
        )

        response = self.client.get("/api/v1/search/", {"q": "Novák", "types": "news"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.data["news"][:2]],
            [self.news.id, older_by_publish_date.id],
        )

    def test_types_filter_excludes_other_types(self):
        response = self.client.get("/api/v1/search/", {"q": "Novák", "types": "riders"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["events"], [])
        self.assertEqual(response.data["news"], [])

    def test_limit_parameter_respected(self):
        for i in range(5):
            Rider.objects.create(
                uci_id=99900010 + i,
                first_name="Novák",
                last_name=f"Extra{i}",
                date_of_birth=date(2005, 1, 1),
                is_active=True,
                is_approved=True,
            )
        response = self.client.get("/api/v1/search/", {"q": "Novák", "limit": "2", "types": "riders"})
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.data["riders"]), 2)

    def test_unauthenticated_access_allowed(self):
        response = self.client.get("/api/v1/search/", {"q": "Novák"})
        self.assertEqual(response.status_code, 200)

    def test_response_contains_query_field(self):
        response = self.client.get("/api/v1/search/", {"q": "novak"})
        self.assertEqual(response.data["query"], "novak")

    def test_rider_result_contains_required_fields(self):
        response = self.client.get("/api/v1/search/", {"q": "Novák", "types": "riders"})
        self.assertEqual(response.status_code, 200)
        if response.data["riders"]:
            rider = response.data["riders"][0]
            for field in ("uci_id", "first_name", "last_name", "club"):
                self.assertIn(field, rider)

    def test_event_result_contains_required_fields(self):
        response = self.client.get("/api/v1/search/", {"q": "Pohár", "types": "events"})
        self.assertEqual(response.status_code, 200)
        if response.data["events"]:
            event = response.data["events"][0]
            for field in ("id", "name", "date", "organizer"):
                self.assertIn(field, event)


# ===========================================================================
# PromoCodeValidateAPIView — POST /api/v1/promo-codes/validate/
# ===========================================================================

class PromoCodeValidateAPITests(TestCase):
    def setUp(self):
        self.user = make_user(username="validate_user", email="validate@example.com")
        self.client = _auth_client(self.user)
        self.url = "/api/v1/promo-codes/validate/"

    def test_valid_code_returns_true(self):
        promo = _make_promo(discount_type=PromoCode.DISCOUNT_FREE)
        response = self.client.post(self.url, {"code": promo.code, "product": PromoCode.PRODUCT_MOBILE_APP})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["valid"])
        self.assertIn("discount_type", response.data)
        self.assertIn("discount_value", response.data)

    def test_nonexistent_code_returns_invalid(self):
        response = self.client.post(self.url, {"code": "DOESNOTEXIST", "product": PromoCode.PRODUCT_MOBILE_APP})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["valid"])
        self.assertIn("error", response.data)

    def test_inactive_code_returns_invalid(self):
        promo = _make_promo(is_active=False)
        response = self.client.post(self.url, {"code": promo.code, "product": PromoCode.PRODUCT_MOBILE_APP})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["valid"])

    def test_expired_code_returns_invalid(self):
        promo = _make_promo(valid_until=timezone.now() - timedelta(days=1))
        response = self.client.post(self.url, {"code": promo.code, "product": PromoCode.PRODUCT_MOBILE_APP})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["valid"])

    def test_exhausted_code_returns_invalid(self):
        promo = _make_promo(max_uses=1)
        promo.used_count = 1
        promo.save(update_fields=["used_count"])
        response = self.client.post(self.url, {"code": promo.code, "product": PromoCode.PRODUCT_MOBILE_APP})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["valid"])

    def test_wrong_product_returns_invalid(self):
        promo = _make_promo(product=PromoCode.PRODUCT_RIDER_STATS)
        response = self.client.post(self.url, {"code": promo.code, "product": PromoCode.PRODUCT_MOBILE_APP})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["valid"])

    def test_product_all_is_valid_for_any_product(self):
        promo = _make_promo(product=PromoCode.PRODUCT_ALL)
        response = self.client.post(self.url, {"code": promo.code, "product": PromoCode.PRODUCT_MOBILE_APP})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["valid"])

    def test_already_used_by_same_user_returns_invalid(self):
        promo = _make_promo()
        PromoCodeUsage.objects.create(
            promo_code=promo,
            user=self.user,
            product=PromoCode.PRODUCT_MOBILE_APP,
            discount_applied=0,
        )
        response = self.client.post(self.url, {"code": promo.code, "product": PromoCode.PRODUCT_MOBILE_APP})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["valid"])

    def test_unauthenticated_returns_401(self):
        promo = _make_promo()
        response = APIClient().post(self.url, {"code": promo.code})
        self.assertEqual(response.status_code, 401)


# ===========================================================================
# PromoCodeGenerateAPIView — POST /api/v1/promo-codes/generate/
# ===========================================================================

class PromoCodeGenerateAPITests(TestCase):
    def setUp(self):
        self.admin = _make_credited_user("gen_admin", is_staff=True, is_superuser=True)
        self.user = make_user(username="gen_user", email="gen@example.com")
        self.admin_client = _auth_client(self.admin)
        self.url = "/api/v1/promo-codes/generate/"

    def test_admin_can_generate_code(self):
        response = self.admin_client.post(self.url, {
            "product": PromoCode.PRODUCT_MOBILE_APP,
            "discount_type": PromoCode.DISCOUNT_FREE,
            "discount_value": 100,
        })
        self.assertEqual(response.status_code, 201)
        self.assertIn("code", response.data)
        self.assertTrue(PromoCode.objects.filter(code=response.data["code"]).exists())

    def test_non_admin_returns_403(self):
        client = _auth_client(self.user)
        response = client.post(self.url, {
            "product": PromoCode.PRODUCT_MOBILE_APP,
            "discount_type": PromoCode.DISCOUNT_FREE,
        })
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_returns_401(self):
        response = APIClient().post(self.url, {"product": PromoCode.PRODUCT_MOBILE_APP})
        self.assertEqual(response.status_code, 401)

    def test_invalid_product_returns_400(self):
        response = self.admin_client.post(self.url, {
            "product": "invalid_product",
            "discount_type": PromoCode.DISCOUNT_FREE,
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)

    def test_invalid_discount_type_returns_400(self):
        response = self.admin_client.post(self.url, {
            "product": PromoCode.PRODUCT_MOBILE_APP,
            "discount_type": "invalid_type",
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)

    def test_response_contains_required_fields(self):
        response = self.admin_client.post(self.url, {
            "product": PromoCode.PRODUCT_RIDER_STATS,
            "discount_type": PromoCode.DISCOUNT_PERCENT,
            "discount_value": 50,
            "max_uses": 10,
        })
        self.assertEqual(response.status_code, 201)
        for field in ("code", "product", "discount_type", "discount_value", "max_uses", "valid_until"):
            self.assertIn(field, response.data)
        self.assertEqual(response.data["product"], PromoCode.PRODUCT_RIDER_STATS)
        self.assertEqual(response.data["discount_value"], 50)
        self.assertEqual(response.data["max_uses"], 10)

    def test_generated_code_persisted_with_correct_fields(self):
        response = self.admin_client.post(self.url, {
            "product": PromoCode.PRODUCT_MOBILE_APP,
            "discount_type": PromoCode.DISCOUNT_FIXED,
            "discount_value": 200,
            "max_uses": 5,
        })
        self.assertEqual(response.status_code, 201)
        promo = PromoCode.objects.get(code=response.data["code"])
        self.assertEqual(promo.discount_type, PromoCode.DISCOUNT_FIXED)
        self.assertEqual(promo.discount_value, 200)
        self.assertEqual(promo.max_uses, 5)
        self.assertEqual(promo.created_by, self.admin)


# ===========================================================================
# MobileAppSubscriptionAPIView — GET/POST/DELETE /api/v1/subscriptions/mobile/
# ===========================================================================

class MobileAppSubscriptionAPITests(TestCase):
    def setUp(self):
        self.season = _make_season(price=499)
        self.user = _make_credited_user("mobsub_user", credit=600)
        self.client = _auth_client(self.user)
        self.url = "/api/v1/subscriptions/mobile/"

    def test_get_returns_status_and_price_when_no_subscription(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("subscription", response.data)
        self.assertIn("price", response.data)
        self.assertIn("balance", response.data)
        self.assertIsNone(response.data["subscription"])
        self.assertEqual(response.data["price"], 499)

    def test_get_returns_active_subscription_data(self):
        from rider.mobile_subscriptions import purchase_mobile_app_subscription
        purchase_mobile_app_subscription(self.user)
        self.user.refresh_from_db()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.data["subscription"])
        self.assertEqual(response.data["subscription"]["status"], MobileAppSubscription.STATUS_ACTIVE)

    def test_post_activates_subscription_and_deducts_credit(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["created"])
        self.assertEqual(response.data["new_balance"], 600 - 499)
        self.assertTrue(MobileAppSubscription.objects.filter(user=self.user, status=MobileAppSubscription.STATUS_ACTIVE).exists())

    def test_post_with_insufficient_credit_returns_400(self):
        broke_user = _make_credited_user("mobsub_broke", credit=100)
        client = _auth_client(broke_user)
        response = client.post(self.url, {})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)

    def test_post_with_free_promo_code_activates_for_zero_credit(self):
        broke_user = _make_credited_user("mobsub_promo", credit=0)
        client = _auth_client(broke_user)
        promo = _make_promo(discount_type=PromoCode.DISCOUNT_FREE)
        response = client.post(self.url, {"promo_code": promo.code})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["new_balance"], 0)

    def test_post_idempotent_when_already_active(self):
        from rider.mobile_subscriptions import purchase_mobile_app_subscription
        purchase_mobile_app_subscription(self.user)
        self.user.refresh_from_db()
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["created"])

    def test_delete_cancels_subscription(self):
        from rider.mobile_subscriptions import purchase_mobile_app_subscription
        purchase_mobile_app_subscription(self.user)
        self.user.refresh_from_db()
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        sub = MobileAppSubscription.objects.get(user=self.user)
        self.assertFalse(sub.auto_renew)

    def test_delete_without_subscription_returns_400(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)

    def test_unauthenticated_returns_401(self):
        for method in ("get", "post", "delete"):
            response = getattr(APIClient(), method)(self.url)
            self.assertEqual(response.status_code, 401, msg=f"Expected 401 for {method.upper()}")


# ===========================================================================
# MobileAppSubscriptionResumeAPIView — POST /api/v1/subscriptions/mobile/resume/
# ===========================================================================

class MobileAppSubscriptionResumeAPITests(TestCase):
    def setUp(self):
        self.season = _make_season(price=499)
        self.user = _make_credited_user("resume_user", credit=600)
        self.client = _auth_client(self.user)
        self.url = "/api/v1/subscriptions/mobile/resume/"

    def _activate_and_cancel(self):
        from rider.mobile_subscriptions import cancel_mobile_app_subscription, purchase_mobile_app_subscription
        sub, _ = purchase_mobile_app_subscription(self.user)
        cancel_mobile_app_subscription(sub)
        return sub

    def test_resume_enables_auto_renew(self):
        sub = self._activate_and_cancel()
        self.assertFalse(sub.auto_renew)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        sub.refresh_from_db()
        self.assertTrue(sub.auto_renew)

    def test_resume_without_subscription_returns_400(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)

    def test_unauthenticated_returns_401(self):
        response = APIClient().post(self.url)
        self.assertEqual(response.status_code, 401)


class APIErrorFormatTests(TestCase):
    """Ověřuje, že každá chybová odpověď API má konzistentní klíč 'error'
    (přidává ho api.exceptions.api_exception_handler), bez ztráty 'detail'/field chyb."""

    def setUp(self):
        cache.clear()  # reset rate-limit bucketů mezi testy

    def test_unauthenticated_error_has_error_key(self):
        # 401 z auth (DRF detail) → handler doplní 'error'
        response = APIClient().get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 401)
        self.assertIn("error", response.data)
        self.assertIsInstance(response.data["error"], str)
        # původní detail zůstává zachován (aditivně)
        self.assertIn("detail", response.data)

    def test_validation_error_has_error_key_and_keeps_fields(self):
        # Špatný login → validační/auth chyba; musí mít 'error' string
        response = APIClient().post("/api/v1/auth/login/", {"email": "x@y.cz", "password": "bad"})
        self.assertGreaterEqual(response.status_code, 400)
        self.assertIn("error", response.data)
        self.assertIsInstance(response.data["error"], str)


class EventControlAPITests(TestCase):
    """API pro import přihlášených jezdců do BMX Event Control.

    Autentizace je HTTP Basic proti údajům organizace (Club.event_control_*),
    závod se adresuje kódem závodu (Event.event_code).
    """

    def setUp(self):
        cache.clear()  # reset throttle bucketu event_control
        self.client = APIClient()
        self.club = Club.objects.create(team_name="BMX Praha")
        self.other_club = Club.objects.create(team_name="BMX Brno")
        self.password = self.club.generate_event_control_credentials()
        self.other_password = self.other_club.generate_event_control_credentials()
        self.event = Event.objects.create(
            name="Český pohár Praha",
            date=date(2026, 5, 10),
            organizer=self.club,
            type_for_ranking="Český pohár",
        )
        self.rider = Rider.objects.create(
            uci_id=100000011,
            first_name="Adam",
            last_name="Novák",
            gender="Muž",
            date_of_birth=date(2012, 1, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            plate_text="12",
            transponder_20="1234",
            transponder_24="5678",
        )
        self.entry = Entry.objects.create(
            event=self.event,
            rider=self.rider,
            is_20=True,
            is_24=True,
            class_20="Boys 14",
            class_24="Cruiser 13-14",
            fee_20=300,
            fee_24=200,
            payment_complete=True,
        )
        self.unpaid_entry = Entry.objects.create(
            event=self.event,
            rider=self.rider,
            is_20=True,
            class_20="Boys 14",
            fee_20=300,
            payment_complete=False,
        )
        self.entries_url = f"/api/v1/event-control/events/{self.event.event_code}/entries/"

    def _auth(self, username, password):
        self.client.credentials(
            HTTP_AUTHORIZATION="Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
        )

    def test_event_gets_unique_code_on_create(self):
        other_event = Event.objects.create(name="Volný závod", organizer=self.club)
        self.assertIsNotNone(self.event.event_code)
        self.assertNotEqual(self.event.event_code, other_event.event_code)

    def test_entries_require_credentials(self):
        response = self.client.get(self.entries_url)
        self.assertEqual(response.status_code, 401)
        self.assertIn("Basic", response["WWW-Authenticate"])

    def test_entries_reject_wrong_password(self):
        self._auth(self.club.event_control_username, "spatne-heslo")
        response = self.client.get(self.entries_url)
        self.assertEqual(response.status_code, 401)

    def test_entries_reject_disabled_access(self):
        self.club.revoke_event_control_credentials()
        self._auth(self.club.event_control_username, self.password)
        response = self.client.get(self.entries_url)
        self.assertEqual(response.status_code, 401)

    def test_entries_reject_other_organizer(self):
        self._auth(self.other_club.event_control_username, self.other_password)
        response = self.client.get(self.entries_url)
        self.assertEqual(response.status_code, 403)

    def test_entries_reject_unknown_event_code(self):
        self._auth(self.club.event_control_username, self.password)
        response = self.client.get(f"/api/v1/event-control/events/{uuid.uuid4()}/entries/")
        self.assertEqual(response.status_code, 403)

    def test_entries_return_paid_starts(self):
        self._auth(self.club.event_control_username, self.password)
        response = self.client.get(self.entries_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["event"]["code"], str(self.event.event_code))
        self.assertEqual(response.data["count"], 1)
        rider = response.data["riders"][0]
        self.assertEqual(rider["uci_id"], "100000011")
        self.assertEqual(rider["club"], "BMX Praha")
        self.assertEqual(rider["sex"], "m")
        self.assertEqual([start["wheel"] for start in rider["starts"]], ["20", "24"])
        self.assertEqual(rider["starts"][0]["class"], "Boys 14")
        self.assertEqual(rider["starts"][0]["plate"], "12")
        self.assertEqual(rider["starts"][0]["transponder"], "1234")
        self.assertEqual(rider["starts"][1]["transponder"], "5678")
        self.assertEqual(rider["fee_total"], 500)

    def test_entries_can_include_unpaid(self):
        self._auth(self.club.event_control_username, self.password)
        response = self.client.get(self.entries_url, {"include_unpaid": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)

    def test_entries_skip_checked_out_entry(self):
        # update() obchází validaci checkoutu (ta vyžaduje uživatele a refund kontext)
        Entry.objects.filter(pk=self.entry.pk).update(checkout=True)
        self._auth(self.club.event_control_username, self.password)
        response = self.client.get(self.entries_url)
        self.assertEqual(response.data["count"], 0)

    def test_ping_returns_organization_and_event_codes(self):
        self._auth(self.club.event_control_username, self.password)
        response = self.client.get("/api/v1/event-control/ping/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["organization"], "BMX Praha")
        self.assertEqual(response.data["events"][0]["code"], str(self.event.event_code))
        self.club.refresh_from_db()
        self.assertIsNotNone(self.club.event_control_last_access)

    def test_event_detail_returns_metadata(self):
        self._auth(self.club.event_control_username, self.password)
        response = self.client.get(f"/api/v1/event-control/events/{self.event.event_code}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "Český pohár Praha")
        self.assertEqual(response.data["organizer"], "BMX Praha")

    def test_event_code_is_not_exposed_in_public_event_list(self):
        response = APIClient().get("/api/v1/events/")
        self.assertEqual(response.status_code, 200)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertNotIn("event_code", results[0])

    def test_generated_password_is_stored_only_as_hash(self):
        self.club.refresh_from_db()
        self.assertNotEqual(self.club.event_control_password, self.password)
        self.assertTrue(self.club.check_event_control_password(self.password))
        self.assertFalse(self.club.check_event_control_password("jine-heslo"))


@override_settings(
    EVENT_CONTROL_CENTRAL_USERNAME="event-control-admin",
    EVENT_CONTROL_CENTRAL_PASSWORD="central-secret",
)
class EventControlMasterDataAPITests(TestCase):
    """Výdej master dat (jezdci, kluby) pro centrální Event Control Admin."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.club = Club.objects.create(team_name="BMX Praha", ico="12345678", city="Praha")
        self.inactive_club = Club.objects.create(team_name="BMX Zaniklý", is_active=False)
        self.rider = Rider.objects.create(
            uci_id=100000021,
            first_name="Adam",
            last_name="Novák",
            gender="Muž",
            date_of_birth=date(2012, 1, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            plate_text="12",
            transponder_20="1234",
        )
        self.unapproved_rider = Rider.objects.create(
            uci_id=100000022,
            first_name="Eva",
            last_name="Svobodová",
            gender="Žena",
            date_of_birth=date(2011, 1, 1),
            is_active=True,
            is_approved=False,
        )

    def _central_auth(self, username="event-control-admin", password="central-secret"):
        self.client.credentials(
            HTTP_AUTHORIZATION="Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
        )

    def test_riders_require_central_credentials(self):
        response = self.client.get("/api/v1/event-control/riders/")
        self.assertEqual(response.status_code, 401)

    def test_riders_reject_organizer_credentials(self):
        password = self.club.generate_event_control_credentials()
        self._central_auth(self.club.event_control_username, password)
        response = self.client.get("/api/v1/event-control/riders/")
        self.assertEqual(response.status_code, 401)

    def test_riders_return_approved_active_riders(self):
        self._central_auth()
        response = self.client.get("/api/v1/event-control/riders/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        rider = response.data["results"][0]
        self.assertEqual(rider["uci_id"], "100000021")
        self.assertEqual(rider["club"], "BMX Praha")
        self.assertEqual(rider["plate"], "12")
        self.assertEqual(rider["transponder_20"], "1234")
        self.assertEqual(rider["sex"], "m")

    def test_riders_can_include_inactive_and_unapproved(self):
        self._central_auth()
        response = self.client.get("/api/v1/event-control/riders/", {"include_inactive": "1"})
        self.assertEqual(response.data["count"], 2)

    def test_riders_support_incremental_and_paging(self):
        self._central_auth()
        response = self.client.get("/api/v1/event-control/riders/", {"updated_since": "2099-01-01"})
        self.assertEqual(response.data["count"], 0)

        response = self.client.get("/api/v1/event-control/riders/", {"limit": "1", "include_inactive": "1"})
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["next_offset"], 1)

    def test_riders_reject_invalid_updated_since(self):
        self._central_auth()
        response = self.client.get("/api/v1/event-control/riders/", {"updated_since": "vcera"})
        self.assertEqual(response.status_code, 400)

    def test_clubs_return_active_clubs(self):
        self._central_auth()
        response = self.client.get("/api/v1/event-control/clubs/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["team_name"], "BMX Praha")
        self.assertEqual(response.data["results"][0]["ico"], "12345678")


class RegistrationApiV1RegistrationsTests(TestCase):
    """Obecný kontrakt v1 — přihlášky závodu (jedna registrace = jeden start)."""

    def setUp(self):
        cache.clear()  # reset throttle bucketu event_control
        self.client = APIClient()
        self.club = Club.objects.create(team_name="BMX Praha")
        self.other_club = Club.objects.create(team_name="BMX Brno")
        self.password = self.club.generate_event_control_credentials()
        self.other_password = self.other_club.generate_event_control_credentials()
        self.event = Event.objects.create(
            name="Český pohár Praha",
            date=date(2026, 5, 10),
            organizer=self.club,
            type_for_ranking="Český pohár",
        )
        self.rider = Rider.objects.create(
            uci_id=100000031,
            first_name="Adam",
            last_name="Novák",
            gender="Muž",
            nationality="CZE",
            date_of_birth=date(2012, 1, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            plate_text="12",
            transponder_20="1234",
            transponder_24="5678",
        )
        self.entry = Entry.objects.create(
            event=self.event,
            rider=self.rider,
            is_20=True,
            is_24=True,
            class_20="Boys 14",
            class_24="Cruiser 13-14",
            fee_20=300,
            fee_24=200,
            payment_complete=True,
        )
        self.url = f"/api/registration/v1/events/{self.event.event_code}/registrations"

    def _auth(self, username, password):
        self.client.credentials(
            HTTP_AUTHORIZATION="Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
        )

    def test_requires_organization_credentials(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)
        self.assertIn("Basic", response["WWW-Authenticate"])

    def test_rejects_other_organizer(self):
        self._auth(self.other_club.event_control_username, self.other_password)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_unknown_event_code_looks_the_same_as_forbidden(self):
        self._auth(self.club.event_control_username, self.password)
        response = self.client.get(f"/api/registration/v1/events/{uuid.uuid4()}/registrations")
        self.assertEqual(response.status_code, 403)

    def test_malformed_event_code_does_not_raise(self):
        """Překlep v „Kód závodu pro API“ nesmí skončit chybou 500."""
        self._auth(self.club.event_control_username, self.password)
        response = self.client.get("/api/registration/v1/events/RACE-2026-001/registrations")
        self.assertEqual(response.status_code, 403)

    def test_one_registration_per_start(self):
        self._auth(self.club.event_control_username, self.password)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["schema_version"], "1.0")
        self.assertEqual(response.data["count"], 2)
        self.assertIsNone(response.data["next_page"])

        twenty, cruiser = response.data["registrations"]
        self.assertEqual(twenty["category"], {"code": "Boys 14", "name": "Boys 14", "wheel_size": 20})
        self.assertEqual(cruiser["category"]["wheel_size"], 24)
        self.assertEqual(twenty["status"], "confirmed")
        # Stejný jezdec, dva starty — uci_id je společné, registration_id ne.
        self.assertEqual(twenty["rider"]["uci_id"], cruiser["rider"]["uci_id"])
        self.assertNotEqual(twenty["registration_id"], cruiser["registration_id"])

    def test_rider_fields_match_contract(self):
        self._auth(self.club.event_control_username, self.password)
        rider = self.client.get(self.url).data["registrations"][0]["rider"]

        self.assertEqual(rider["uci_id"], "100000031")
        self.assertEqual(rider["first_name"], "Adam")
        self.assertEqual(rider["last_name"], "Novák")
        self.assertEqual(rider["birth_date"], "2012-01-01")
        self.assertEqual(rider["gender"], "M")
        self.assertIs(rider["elite"], False)
        self.assertEqual(rider["nationality"], "CZE")
        self.assertEqual(rider["club"], "BMX Praha")
        self.assertEqual(rider["bib"], 12)

    def test_chip_belongs_to_the_wheel_of_its_start(self):
        self._auth(self.club.event_control_username, self.password)
        twenty, cruiser = self.client.get(self.url).data["registrations"]

        self.assertEqual(twenty["rider"]["chip_id_20"], "1234")
        self.assertEqual(twenty["rider"]["chip_id_24"], "")
        self.assertEqual(cruiser["rider"]["chip_id_24"], "5678")
        self.assertEqual(cruiser["rider"]["chip_id_20"], "")

    def test_championship_plate_wins_and_stays_numeric(self):
        """Championship tabulka má přednost, ale bez prefixu ``W``.

        REM export píše ``W123``, protože ho čte člověk. Startovní číslo
        v závodním software je celé číslo, takže do kontraktu jde 123.
        """
        self.rider.is_elite = True
        self.rider.plate_champ_20 = 118
        self.rider.save()

        self._auth(self.club.event_control_username, self.password)
        registrations = self.client.get(self.url).data["registrations"]

        self.assertEqual(registrations[0]["rider"]["bib"], 118)
        self.assertIs(registrations[0]["rider"]["elite"], True)
        # 24" championship tabulku jezdec nemá — zůstává národní.
        self.assertEqual(registrations[1]["rider"]["bib"], 12)

    def test_letters_in_plate_do_not_become_a_number(self):
        """Tabulka ``123A`` není číslo — nesmí se z ní stát 0 ani 123."""
        self.rider.plate_text = "12A"
        self.rider.save()

        self._auth(self.club.event_control_username, self.password)
        registrations = self.client.get(self.url).data["registrations"]
        self.assertIsNone(registrations[0]["rider"]["bib"])

    def test_unpaid_entries_are_left_out_unless_asked_for(self):
        Entry.objects.create(
            event=self.event,
            rider=self.rider,
            is_20=True,
            class_20="Boys 14",
            fee_20=300,
            payment_complete=False,
        )
        self._auth(self.club.event_control_username, self.password)

        self.assertEqual(self.client.get(self.url).data["count"], 2)

        response = self.client.get(self.url, {"include_unpaid": "1"})
        self.assertEqual(response.data["count"], 3)
        # Dvě přihlášky téhož jezdce mají stejné řadicí jméno, takže se na
        # jejich pořadí spolehnout nelze — kontroluje se počet stavů.
        statuses = [row["status"] for row in response.data["registrations"]]
        self.assertEqual(statuses.count("pending"), 1)
        self.assertEqual(statuses.count("confirmed"), 2)

    def test_paging_walks_forward_and_stops(self):
        self._auth(self.club.event_control_username, self.password)

        first = self.client.get(self.url, {"page": "1", "page_size": "1"})
        self.assertEqual(first.data["count"], 2)
        self.assertEqual(len(first.data["registrations"]), 1)
        self.assertEqual(first.data["next_page"], 2)

        second = self.client.get(self.url, {"page": "2", "page_size": "1"})
        self.assertEqual(len(second.data["registrations"]), 1)
        self.assertIsNone(second.data["next_page"])
        self.assertNotEqual(
            first.data["registrations"][0]["registration_id"],
            second.data["registrations"][0]["registration_id"],
        )

    def test_registration_id_is_stable_across_imports(self):
        self._auth(self.club.event_control_username, self.password)
        first = self.client.get(self.url).data["registrations"]
        second = self.client.get(self.url).data["registrations"]
        self.assertEqual(
            [row["registration_id"] for row in first],
            [row["registration_id"] for row in second],
        )

    def test_trailing_slash_serves_the_same_payload(self):
        self._auth(self.club.event_control_username, self.password)
        response = self.client.get(self.url + "/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)


@override_settings(
    EVENT_CONTROL_CENTRAL_USERNAME="event-control-admin",
    EVENT_CONTROL_CENTRAL_PASSWORD="central-secret",
)
class RegistrationApiV1MasterDataTests(TestCase):
    """Obecný kontrakt v1 — jezdci a kluby pro centrální registr."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.club = Club.objects.create(
            team_name="Team Praha Racing",
            club_name="BMX Klub Praha",
            ico="12345678",
            street="Sportovní 12",
            city="Praha",
            zip_code="16000",
        )
        self.inactive_club = Club.objects.create(team_name="BMX Zaniklý", is_active=False)
        self.rider = Rider.objects.create(
            uci_id=100000041,
            first_name="Adam",
            last_name="Novák",
            gender="Muž",
            nationality="CZE",
            date_of_birth=date(2012, 1, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            is_elite=True,
            plate_text="12",
            plate_champ_20=118,
            transponder_20="1234",
            transponder_24="5678",
        )
        self.unapproved_rider = Rider.objects.create(
            uci_id=100000042,
            first_name="Eva",
            last_name="Svobodová",
            gender="Žena",
            date_of_birth=date(2011, 1, 1),
            is_active=True,
            is_approved=False,
        )

    def _central_auth(self, username="event-control-admin", password="central-secret"):
        self.client.credentials(
            HTTP_AUTHORIZATION="Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
        )

    def test_riders_require_central_credentials(self):
        self.assertEqual(self.client.get("/api/registration/v1/riders").status_code, 401)

    def test_riders_reject_organizer_credentials(self):
        password = self.club.generate_event_control_credentials()
        self._central_auth(self.club.event_control_username, password)
        self.assertEqual(self.client.get("/api/registration/v1/riders").status_code, 401)

    def test_rider_record_matches_contract(self):
        self._central_auth()
        response = self.client.get("/api/registration/v1/riders")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["schema_version"], "1.0")
        self.assertEqual(response.data["count"], 1)

        rider = response.data["results"][0]
        self.assertEqual(rider["external_id"], str(self.rider.id))
        self.assertEqual(rider["uci_id"], "100000041")
        self.assertEqual(rider["birth_date"], "2012-01-01")
        self.assertEqual(rider["gender"], "M")
        self.assertEqual(rider["nationality"], "CZE")
        self.assertIs(rider["elite"], True)
        self.assertEqual(rider["bib"], 12)
        self.assertEqual(rider["world_bib"], 118)
        self.assertEqual(rider["chip_id_20"], "1234")
        self.assertEqual(rider["chip_id_24"], "5678")
        self.assertEqual(rider["club"], "Team Praha Racing")
        self.assertEqual(rider["club_external_id"], str(self.club.id))
        self.assertIsNotNone(rider["updated"])

    def test_woman_is_reported_as_f(self):
        self._central_auth()
        response = self.client.get("/api/registration/v1/riders", {"include_inactive": "1"})
        genders = {row["uci_id"]: row["gender"] for row in response.data["results"]}
        self.assertEqual(genders["100000042"], "F")

    def test_club_record_matches_contract(self):
        self._central_auth()
        response = self.client.get("/api/registration/v1/clubs")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        club = response.data["results"][0]
        self.assertEqual(club["external_id"], str(self.club.id))
        # `name` je jméno klubu, `team_name` jméno, pod kterým jezdí.
        self.assertEqual(club["name"], "BMX Klub Praha")
        self.assertEqual(club["team_name"], "Team Praha Racing")
        self.assertEqual(club["street"], "Sportovní 12")
        self.assertEqual(club["city"], "Praha")
        self.assertEqual(club["postal_code"], "16000")
        self.assertEqual(club["country"], "CZE")
        self.assertEqual(club["company_id"], "12345678")

    def test_club_without_official_name_falls_back_to_team_name(self):
        self.club.club_name = ""
        self.club.save()
        self._central_auth()
        club = self.client.get("/api/registration/v1/clubs").data["results"][0]
        self.assertEqual(club["name"], "Team Praha Racing")

    def test_inactive_records_are_left_out_unless_asked_for(self):
        self._central_auth()
        self.assertEqual(self.client.get("/api/registration/v1/riders").data["count"], 1)
        self.assertEqual(self.client.get("/api/registration/v1/clubs").data["count"], 1)

        riders = self.client.get("/api/registration/v1/riders", {"include_inactive": "1"})
        clubs = self.client.get("/api/registration/v1/clubs", {"include_inactive": "1"})
        self.assertEqual(riders.data["count"], 2)
        self.assertEqual(clubs.data["count"], 2)

    def test_incremental_and_offset_paging(self):
        self._central_auth()
        empty = self.client.get("/api/registration/v1/riders", {"updated_since": "2099-01-01"})
        self.assertEqual(empty.data["count"], 0)
        self.assertIsNone(empty.data["next_offset"])

        page = self.client.get(
            "/api/registration/v1/riders", {"limit": "1", "include_inactive": "1"}
        )
        self.assertEqual(len(page.data["results"]), 1)
        self.assertEqual(page.data["next_offset"], 1)

        last = self.client.get(
            "/api/registration/v1/riders",
            {"limit": "1", "offset": "1", "include_inactive": "1"},
        )
        self.assertIsNone(last.data["next_offset"])

    def test_generated_at_is_the_watermark_for_the_next_run(self):
        self._central_auth()
        response = self.client.get("/api/registration/v1/riders")
        self.assertIsNotNone(response.data["generated_at"])

    def test_reject_invalid_updated_since(self):
        self._central_auth()
        response = self.client.get("/api/registration/v1/riders", {"updated_since": "vcera"})
        self.assertEqual(response.status_code, 400)


@override_settings(
    EVENT_CONTROL_CENTRAL_USERNAME="event-control-admin",
    EVENT_CONTROL_CENTRAL_PASSWORD="central-secret",
)
class RegistrationApiV1ChipWritebackTests(TestCase):
    """Trvalá změna čipu u rampy se zapíše zpátky do registru webu.

    Bez toho je oprava u rampy jednorázová: Event Control ji má u sebe, ale
    při nejbližší synchronizaci ji stažená hodnota z webu přepíše na starou
    a jezdec začne příští závod zase se špatným čipem.
    """

    URL = "/api/registration/v1/riders/100000041"

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.rider = Rider.objects.create(
            uci_id=100000041,
            first_name="Adam",
            last_name="Novák",
            gender="Muž",
            date_of_birth=date(2012, 1, 1),
            is_active=True,
            is_approved=True,
            transponder_20="AA-10001",
        )

    def _central_auth(self, username="event-control-admin", password="central-secret"):
        self.client.credentials(
            HTTP_AUTHORIZATION="Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
        )

    def _patch(self, body):
        return self.client.patch(self.URL, body, format="json")

    def test_write_requires_central_credentials(self):
        self.assertEqual(self._patch({"chip_id_20": "BB-20002"}).status_code, 401)
        self.rider.refresh_from_db()
        self.assertEqual(self.rider.transponder_20, "AA-10001")

    def test_organizer_credentials_may_not_change_the_federation_registry(self):
        club = Club.objects.create(team_name="BMX Klub Praha")
        password = club.generate_event_control_credentials()
        self._central_auth(club.event_control_username, password)

        self.assertEqual(self._patch({"chip_id_20": "BB-20002"}).status_code, 401)

    def test_permanent_change_lands_in_the_registry_and_in_the_history(self):
        self._central_auth()

        response = self._patch(
            {
                "schema_version": "1.0",
                "chip_id_20": "BB-20002",
                "source": "event-control",
                "changed_by": "jana.novakova",
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["chip_id_20"], "BB-20002")
        self.assertEqual(response.data["changed"], ["20"])
        self.rider.refresh_from_db()
        self.assertEqual(self.rider.transponder_20, "BB-20002")

        history = RiderTransponderChange.objects.get(rider=self.rider)
        self.assertEqual(history.slot, "20")
        self.assertEqual(history.old_transponder, "AA-10001")
        self.assertEqual(history.new_transponder, "BB-20002")

    def test_only_the_wheel_that_was_sent_is_touched(self):
        self.rider.transponder_24 = "CC-24003"
        self.rider.save()
        self._central_auth()

        self._patch({"chip_id_20": "BB-20002"})

        self.rider.refresh_from_db()
        self.assertEqual(self.rider.transponder_24, "CC-24003")

    def test_an_empty_chip_removes_it(self):
        """„Jezdec už čip nemá" je zjištění obsluhy, ne neposlané pole."""
        self._central_auth()

        response = self._patch({"chip_id_20": ""})

        self.assertEqual(response.status_code, 200)
        self.rider.refresh_from_db()
        self.assertIsNone(self.rider.transponder_20)

    def test_repeating_the_same_chip_is_not_an_error(self):
        """Event Control odesílá z fronty — pokus se po výpadku zopakuje."""
        self._central_auth()

        first = self._patch({"chip_id_20": "BB-20002"})
        second = self._patch({"chip_id_20": "BB-20002"})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["changed"], [])
        self.assertEqual(RiderTransponderChange.objects.filter(rider=self.rider).count(), 1)

    def test_unknown_rider_is_404(self):
        self._central_auth()
        response = self.client.patch(
            "/api/registration/v1/riders/109999999", {"chip_id_20": "BB-20002"}, format="json"
        )
        self.assertEqual(response.status_code, 404)

    def test_nonsense_in_the_path_is_404_not_a_broken_body(self):
        """Na 404 se kontrakt nepokouší znovu; na 422 by volající hádal, co v těle."""
        self._central_auth()
        response = self.client.patch(
            "/api/registration/v1/riders/nesmysl", {"chip_id_20": "BB-20002"}, format="json"
        )
        self.assertEqual(response.status_code, 404)

    def test_a_chip_that_belongs_to_someone_else_is_refused(self):
        """Dva jezdci na jednom kódu znamenají cizí průjezdy v časomíře."""
        Rider.objects.create(
            uci_id=100000042,
            first_name="Eva",
            last_name="Svobodová",
            gender="Žena",
            date_of_birth=date(2011, 1, 1),
            is_active=True,
            is_approved=True,
            transponder_20="BB-20002",
        )
        self._central_auth()

        response = self._patch({"chip_id_20": "BB-20002"})

        self.assertEqual(response.status_code, 409)
        self.rider.refresh_from_db()
        self.assertEqual(self.rider.transponder_20, "AA-10001")

    def test_a_body_without_any_chip_is_refused(self):
        self._central_auth()
        self.assertEqual(self._patch({"first_name": "Petr"}).status_code, 422)
        self.rider.refresh_from_db()
        self.assertEqual(self.rider.first_name, "Adam")

    def test_a_chip_longer_than_the_column_is_refused_instead_of_truncated(self):
        self._central_auth()

        response = self._patch({"chip_id_20": "AA-10001-PRILIS-DLOUHY"})

        self.assertEqual(response.status_code, 422)
        self.rider.refresh_from_db()
        self.assertEqual(self.rider.transponder_20, "AA-10001")

    def test_the_uci_id_in_the_path_wins_over_the_body(self):
        """Jinak by se jedním požadavkem dal změnit čip někomu jinému."""
        other = Rider.objects.create(
            uci_id=100000042,
            first_name="Eva",
            last_name="Svobodová",
            gender="Žena",
            date_of_birth=date(2011, 1, 1),
            is_active=True,
            is_approved=True,
        )
        self._central_auth()

        self._patch({"uci_id": "100000042", "chip_id_20": "BB-20002"})

        self.rider.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.rider.transponder_20, "BB-20002")
        self.assertIsNone(other.transponder_20)


@override_settings(
    EVENT_CONTROL_CENTRAL_USERNAME="event-control-admin",
    EVENT_CONTROL_CENTRAL_PASSWORD="central-secret",
)
class EventControlCentralEntriesTests(TestCase):
    """Centrální údaje platí i na přihlášky závodu.

    Nahlášeno z provozu 15. 8. 2026: Event Control se centrálními údaji
    synchronizuje registr jezdců a klubů (HTTP 200), ale na přihlášky dostal
    401 „Neplatné přístupové údaje organizace." — pořadatel tak musel do
    integrace vyplňovat druhý pár údajů jen kvůli přihláškám. Kdo zná centrální
    heslo, čte stejně celý registr federace; přihlášky jednoho závodu tím nejsou
    širší přístup.
    """

    def setUp(self):
        cache.clear()  # reset throttle bucketu event_control
        self.client = APIClient()
        self.organizer = Club.objects.create(team_name="BMX Praha")
        self.event = Event.objects.create(
            name="Český pohár Praha",
            date=date(2026, 5, 10),
            organizer=self.organizer,
            type_for_ranking="Český pohár",
        )
        self.rider = Rider.objects.create(
            uci_id=100000051,
            first_name="Adam",
            last_name="Novák",
            gender="Muž",
            nationality="CZE",
            date_of_birth=date(2012, 1, 1),
            club=self.organizer,
            is_active=True,
            is_approved=True,
            plate_text="12",
            transponder_20="1234",
        )
        Entry.objects.create(
            event=self.event,
            rider=self.rider,
            is_20=True,
            class_20="Boys 14",
            fee_20=300,
            payment_complete=True,
        )
        self.url = f"/api/registration/v1/events/{self.event.event_code}/registrations"

    def _auth(self, username="event-control-admin", password="central-secret"):
        self.client.credentials(
            HTTP_AUTHORIZATION="Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
        )

    def test_central_credentials_read_registrations(self):
        self._auth()
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["schema_version"], "1.0")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["registrations"][0]["rider"]["uci_id"], "100000051"
        )

    def test_central_credentials_are_not_limited_to_one_organizer(self):
        """Centrální identita není pořadatel — nesmí ji zastavit kontrola klubu."""
        other = Club.objects.create(team_name="BMX Brno")
        foreign_event = Event.objects.create(
            name="Cizí závod",
            date=date(2026, 6, 10),
            organizer=other,
            type_for_ranking="Český pohár",
        )
        self._auth()
        response = self.client.get(
            f"/api/registration/v1/events/{foreign_event.event_code}/registrations"
        )

        self.assertEqual(response.status_code, 200)

    def test_central_credentials_work_on_the_legacy_entries_path(self):
        self._auth()
        response = self.client.get(
            f"/api/v1/event-control/events/{self.event.event_code}/entries/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_wrong_central_password_is_still_rejected(self):
        self._auth(password="spatne")
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_unknown_event_code_stays_hidden(self):
        """Ani centrální identita se nesmí dozvědět, že závod neexistuje."""
        self._auth()
        response = self.client.get(
            f"/api/registration/v1/events/{uuid.uuid4()}/registrations"
        )
        self.assertEqual(response.status_code, 403)

    def test_ping_says_central_not_staff(self):
        self._auth()
        response = self.client.get("/api/v1/event-control/ping/")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["organization"])
        self.assertIs(response.data["central"], True)
        self.assertIs(response.data["staff"], False)


class EventControlCentralDisabledTests(TestCase):
    """Bez nastavených centrálních údajů se centrální cestou nedá projít."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.organizer = Club.objects.create(team_name="BMX Praha")
        self.event = Event.objects.create(
            name="Český pohár Praha",
            date=date(2026, 5, 10),
            organizer=self.organizer,
            type_for_ranking="Český pohár",
        )

    def test_empty_central_settings_do_not_authenticate(self):
        self.client.credentials(
            HTTP_AUTHORIZATION="Basic " + base64.b64encode(b":").decode()
        )
        response = self.client.get(
            f"/api/registration/v1/events/{self.event.event_code}/registrations"
        )
        self.assertEqual(response.status_code, 401)
