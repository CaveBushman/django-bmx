from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from io import BytesIO
from PIL import Image
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from types import SimpleNamespace
from unittest.mock import patch

from event.models import CreditTransaction
from news.models import News

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
        self.client = APIClient()
        self.user = make_user()
        self.url = "/api/auth/login/"

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
        response = self.client.post("/api/auth/token/refresh/", {"refresh": str(refresh)})
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    def test_invalid_refresh_token_returns_401(self):
        response = self.client.post("/api/auth/token/refresh/", {"refresh": "invalid.token.here"})
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
        response = self.client.post("/api/auth/logout/", {"refresh": refresh_str})
        self.assertEqual(response.status_code, 204)

    def test_logout_blacklists_refresh_token(self):
        refresh_str = self._auth()
        self.client.post("/api/auth/logout/", {"refresh": refresh_str})
        response = self.client.post("/api/auth/token/refresh/", {"refresh": refresh_str})
        self.assertEqual(response.status_code, 401)

    def test_unauthenticated_logout_returns_401(self):
        response = self.client.post("/api/auth/logout/")
        self.assertEqual(response.status_code, 401)


class MeAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user(username="me_user", email="me@example.com")
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    def test_get_me_returns_user_data(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], "me@example.com")

    def test_patch_me_updates_name(self):
        response = self.client.patch("/api/auth/me/", {"first_name": "Nové", "last_name": "Jméno"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["first_name"], "Nové")
        self.assertEqual(response.data["last_name"], "Jméno")

    def test_patch_me_ignores_disallowed_fields(self):
        original_email = self.user.email
        response = self.client.patch("/api/auth/me/", {"email": "hacker@evil.com"})
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
            "/api/auth/me/",
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
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 401)


class CreditTopUpAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user(username="credit_user", email="credit@example.com")
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    @patch("api.views.stripe.checkout.Session.create")
    def test_credit_topup_creates_stripe_checkout_session(self, create_mock):
        create_mock.return_value = SimpleNamespace(
            id="cs_test_mobile_credit",
            url="https://checkout.stripe.com/c/pay/cs_test_mobile_credit",
        )

        response = self.client.post("/api/credit/topup/", {"amount": 500})

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
        response = self.client.post("/api/credit/topup/", {"amount": 99})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(CreditTransaction.objects.exists())

    def test_credit_topup_requires_authentication(self):
        self.client.credentials()
        response = self.client.post("/api/credit/topup/", {"amount": 500})
        self.assertEqual(response.status_code, 401)


class PasswordChangeAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user(username="pwd_user", email="pwd@example.com")
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    def test_password_change_success(self):
        response = self.client.post(
            "/api/auth/password/change/",
            {"old_password": "StrongPass123!", "new_password": "NewPass456!"},
        )
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPass456!"))

    def test_wrong_old_password_returns_400(self):
        response = self.client.post(
            "/api/auth/password/change/",
            {"old_password": "wrong", "new_password": "NewPass456!"},
        )
        self.assertEqual(response.status_code, 400)

    def test_short_new_password_returns_400(self):
        response = self.client.post(
            "/api/auth/password/change/",
            {"old_password": "StrongPass123!", "new_password": "short"},
        )
        self.assertEqual(response.status_code, 400)


class RiderListAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user(username="rider_api_user", email="rider_api@example.com")
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    def test_rider_list_requires_authentication(self):
        self.client.credentials()
        response = self.client.get("/api/riders/")
        self.assertEqual(response.status_code, 401)

    def test_authenticated_user_can_access_rider_list(self):
        response = self.client.get("/api/riders/")
        self.assertEqual(response.status_code, 200)

    def test_response_is_paginated(self):
        response = self.client.get("/api/riders/")
        self.assertIn("count", response.data)
        self.assertIn("results", response.data)


class NewsListAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_news_list_returns_only_articles_published_in_app(self):
        visible = News.objects.create(
            title="Visible article",
            prefix="prefix",
            content="content",
            published=True,
            publish_in_app=True,
        )
        News.objects.create(
            title="Hidden article",
            prefix="prefix",
            content="content",
            published=True,
            publish_in_app=False,
        )

        response = self.client.get("/api/news/")

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        self.assertEqual([item["id"] for item in response.data], [visible.id])

    def test_news_list_is_not_paginated_and_orders_by_created_date_desc(self):
        older = News.objects.create(
            title="Older article",
            prefix="prefix",
            content="content",
            published=True,
            publish_in_app=True,
        )
        newer = News.objects.create(
            title="Newer article",
            prefix="prefix",
            content="content",
            published=True,
            publish_in_app=True,
        )
        News.objects.filter(pk=older.pk).update(created_date=timezone.now() - timedelta(days=2))
        News.objects.filter(pk=newer.pk).update(created_date=timezone.now() - timedelta(days=1))

        response = self.client.get("/api/news/")

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        self.assertEqual([item["id"] for item in response.data[:2]], [newer.id, older.id])
