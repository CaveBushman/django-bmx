import datetime

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core import mail
from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountActivationAuditLog
from bmx.form_protection import build_flow_token


User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SignUpTests(TestCase):
    def setUp(self):
        cache.clear()

    def signup_payload(self, **overrides):
        payload = {
            "firstname": "DP",
            "lastname": "DP",
            "username": "dp@dp.cz",
            "password": "StrongPass123!",
            "password2": "StrongPass123!",
            "form_token": build_flow_token(
                "signup",
                timezone.now() - datetime.timedelta(seconds=5)
            ),
            "website": "",
        }
        payload.update(overrides)
        return payload

    def test_signup_page_contains_czech_riders_notice(self):
        response = self.client.get(reverse("accounts:signup"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Notice: user registration and credit purchases are intended for Czech riders only.",
        )
        self.assertContains(response, 'name="form_token"', html=False)

    def test_signup_accepts_email_in_username_field(self):
        response = self.client.post(
            reverse("accounts:signup"),
            self.signup_payload(),
        )

        self.assertRedirects(response, reverse("accounts:activation_sent"))
        user = User.objects.get(email="dp@dp.cz")
        self.assertEqual(user.username, "dp@dp.cz")
        self.assertEqual(user.first_name, "DP")
        self.assertEqual(user.last_name, "DP")
        self.assertFalse(user.is_active)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Aktivace účtu na Czech BMX", mail.outbox[0].subject)
        self.assertIn("/accounts/activate/", mail.outbox[0].body)
        self.assertTrue(
            AccountActivationAuditLog.objects.filter(
                account=user,
                action=AccountActivationAuditLog.Action.SENT,
            ).exists()
        )

    def test_signup_rejects_case_insensitive_duplicate_email(self):
        User.objects.create_user(
            first_name="Existing",
            last_name="User",
            username="existing_user",
            email="existing@example.com",
            password="StrongPass123!",
        )

        response = self.client.post(
            reverse("accounts:signup"),
            self.signup_payload(
                firstname="New",
                lastname="User",
                username="EXISTING@EXAMPLE.COM",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(email__iexact="existing@example.com").count(), 1)

    def test_signup_redirects_to_resend_for_existing_inactive_account(self):
        existing = User.objects.create_user(
            first_name="Existing",
            last_name="Pending",
            username="existing_pending",
            email="existing-pending@example.com",
            password="StrongPass123!",
        )
        existing.is_active = False
        existing.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("accounts:signup"),
            self.signup_payload(username="existing-pending@example.com"),
        )

        self.assertRedirects(
            response,
            f"{reverse('accounts:resend_activation')}?email=existing-pending@example.com",
            fetch_redirect_response=False,
        )

    def test_signup_rejects_honeypot_submission(self):
        response = self.client.post(
            reverse("accounts:signup"),
            self.signup_payload(website="Spam Corp"),
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email="dp@dp.cz").exists())

    def test_signup_rejects_too_fast_submission(self):
        response = self.client.post(
            reverse("accounts:signup"),
            self.signup_payload(form_token=build_flow_token("signup", timezone.now())),
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email="dp@dp.cz").exists())

    def test_signup_rate_limits_repeated_robot_attempts(self):
        url = reverse("accounts:signup")
        for _ in range(settings.FORM_PROTECTION["signup"]["rate_limit_max_attempts"]):
            response = self.client.post(
                url,
                self.signup_payload(website="Spam Corp"),
            )
            self.assertEqual(response.status_code, 400)

        blocked_response = self.client.post(url, self.signup_payload())

        self.assertEqual(blocked_response.status_code, 429)
        self.assertFalse(User.objects.filter(email="dp@dp.cz").exists())

    def test_signup_activation_link_activates_account(self):
        self.client.post(reverse("accounts:signup"), self.signup_payload())

        user = User.objects.get(email="dp@dp.cz")
        activation_link = next(
            line.strip()
            for line in mail.outbox[0].body.splitlines()
            if "/accounts/activate/" in line
        )

        response = self.client.get(activation_link.replace("http://testserver", ""))

        self.assertRedirects(response, reverse("accounts:login"))
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_resend_activation_email_sends_new_message(self):
        self.client.post(reverse("accounts:signup"), self.signup_payload())
        mail.outbox.clear()

        response = self.client.post(
            reverse("accounts:resend_activation"),
            {
                "email": "dp@dp.cz",
                "form_token": build_flow_token("activation_resend", timezone.now() - datetime.timedelta(seconds=2)),
                "website": "",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Aktivace účtu na Czech BMX", mail.outbox[0].subject)
        self.assertTrue(
            AccountActivationAuditLog.objects.filter(
                email_snapshot="dp@dp.cz",
                action=AccountActivationAuditLog.Action.RESENT,
            ).exists()
        )
