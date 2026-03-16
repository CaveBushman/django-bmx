from django.contrib.auth import get_user_model
from django.test import TestCase


User = get_user_model()


class RiderApiAccessTests(TestCase):
    def setUp(self):
        self.url = "/api/riders"
        self.user = User.objects.create_user(
            first_name="Api",
            last_name="Tester",
            username="api_tester",
            email="api_tester@example.com",
            password="StrongPass123!",
        )
        self.user.is_active = True
        self.user.save()

    def test_rider_list_requires_authentication(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_authenticated_user_can_access_rider_list(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
