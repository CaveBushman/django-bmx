from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

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

    def test_unauthenticated_me_returns_401(self):
        self.client.credentials()
        response = self.client.get("/api/auth/me/")
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
