from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


User = get_user_model()


class SignUpTests(TestCase):
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
