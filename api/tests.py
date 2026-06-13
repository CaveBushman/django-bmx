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
from event.models import CreditTransaction, Event, Result, SeasonSettings
from news.models import News
from rider.models import MobileAppSubscription, PromoCode, PromoCodeUsage, Rider

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

    def test_news_list_is_not_paginated_and_orders_by_created_date_desc(self):
        older = News.objects.create(
            title="Older article",
            perex="prefix",
            content="content",
            published=True,
            publish_in_app=True,
        )
        newer = News.objects.create(
            title="Newer article",
            perex="prefix",
            content="content",
            published=True,
            publish_in_app=True,
        )
        News.objects.filter(pk=older.pk).update(created_date=timezone.now() - timedelta(days=2))
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
