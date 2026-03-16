from datetime import date

from django.test import TestCase
from django.urls import reverse

from event.models import SeasonSettings


class RulesViewTests(TestCase):
    def test_rules_view_uses_transponder_price_from_current_season(self):
        SeasonSettings.objects.create(
            year=date.today().year,
            transponder_price=2450,
        )

        response = self.client.get(reverse("news:rules"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2450 Kč")
