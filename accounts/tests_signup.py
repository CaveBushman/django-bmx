from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


User = get_user_model()


class SignUpTests(TestCase):
    def test_signup_page_contains_czech_riders_notice(self):
        response = self.client.get(reverse("accounts:signup"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Notice: user registration and credit purchases are intended for Czech riders only.",
        )

    def test_signup_accepts_email_in_username_field(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "firstname": "DP",
                "lastname": "DP",
                "username": "dp@dp.cz",
                "password": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertRedirects(response, reverse("news:homepage"))
        user = User.objects.get(email="dp@dp.cz")
        self.assertEqual(user.username, "dp@dp.cz")
        self.assertEqual(user.first_name, "DP")
        self.assertEqual(user.last_name, "DP")
        self.assertTrue(user.is_active)

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
            {
                "firstname": "New",
                "lastname": "User",
                "username": "EXISTING@EXAMPLE.COM",
                "password": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(email__iexact="existing@example.com").count(), 1)
