from datetime import timedelta

from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from admin_stats.middleware import VisitMiddleware
from admin_stats.models import Visit


class VisitStatsViewTests(TestCase):
    def setUp(self):
        recent_time = timezone.now() - timedelta(days=1)
        older_time = timezone.now() - timedelta(days=10)

        first = Visit.objects.create(
            ip_address="10.0.0.1",
            user_agent="Mozilla",
            location="Czech Republic",
            device_type="Desktop",
        )
        second = Visit.objects.create(
            ip_address="10.0.0.2",
            user_agent="Mozilla Mobile",
            location="Germany",
            device_type="Mobile",
        )
        old = Visit.objects.create(
            ip_address="10.0.0.3",
            user_agent="Legacy",
            location="Austria",
            device_type="Tablet",
        )

        Visit.objects.filter(pk__in=[first.pk, second.pk]).update(timestamp=recent_time)
        Visit.objects.filter(pk=old.pk).update(timestamp=older_time)

    def test_visit_stats_exposes_locations_and_devices_for_template(self):
        response = self.client.get(reverse("admin_stats:visit_stats"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_visits"], 2)
        self.assertEqual(response.context["unique_visits"], 2)
        self.assertEqual(response.context["top_locations"][0], ("Czech Republic", 1))
        self.assertIn(("Germany", 1), response.context["top_locations"])
        self.assertIn(("Desktop", 1), response.context["device_stats"])
        self.assertIn(("Mobile", 1), response.context["device_stats"])


class VisitMiddlewareTests(TestCase):
    @override_settings(DEBUG=True)
    def test_middleware_skips_visit_logging_in_debug_mode(self):
        request = RequestFactory().get("/bmx-admin/")

        VisitMiddleware(lambda req: None).process_request(request)

        self.assertEqual(Visit.objects.count(), 0)
