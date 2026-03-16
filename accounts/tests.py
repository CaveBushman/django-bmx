from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse


User = get_user_model()


class RememberMeLoginTests(TestCase):
    def setUp(self):
        self.password = "StrongPass123!"
        self.user = User.objects.create_user(
            first_name="Remember",
            last_name="Tester",
            username="remember_tester",
            email="remember@example.com",
            password=self.password,
        )
        self.user.is_active = True
        self.user.save()

    def test_login_with_remember_me_sets_persistent_session(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": self.user.email,
                "password": self.password,
                "remember-me": "on",
            },
        )

        self.assertRedirects(response, reverse("news:homepage"))
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertEqual(self.client.session.get_expiry_age(), 1209600)

    def test_login_without_remember_me_expires_at_browser_close(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": self.user.email,
                "password": self.password,
            },
        )

        self.assertRedirects(response, reverse("news:homepage"))
        self.assertTrue(self.client.session.get_expire_at_browser_close())


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetTests(TestCase):
    def setUp(self):
        self.password = "StrongPass123!"
        self.user = User.objects.create_user(
            first_name="Reset",
            last_name="Tester",
            username="reset_tester",
            email="reset@example.com",
            password=self.password,
        )
        self.user.is_active = True
        self.user.save()

    def test_password_reset_sends_email(self):
        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": self.user.email},
        )

        self.assertRedirects(
            response,
            reverse("accounts:password_reset_done"),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Reset hesla na Czech BMX", mail.outbox[0].subject)
        self.assertIn("/accounts/reset/", mail.outbox[0].body)
