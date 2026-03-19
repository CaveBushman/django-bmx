from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from .models import News
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


class NewsModelTests(TestCase):

    @patch('news.models._EXECUTOR.submit')
    def test_slug_and_tts_generation_on_save(self, mock_submit):
        # 1. Vytvoření nového publikovaného článku
        article = News.objects.create(
            title="Testovací článek pro slug",
            content="Nějaký obsah.",
            published=True
        )

        # Ověření, že se vygeneroval slug
        self.assertEqual(article.slug, "testovaci-clanek-pro-slug")

        # Ověření, že se při prvním uložení zaplánovalo generování TTS
        mock_submit.assert_called_once_with(article.__class__._generate_audio, article.pk)

        # Reset mocku
        mock_submit.reset_mock()

        # 2. Uložení článku bez změny obsahu
        article.on_homepage = True
        article.save()

        # Ověření, že se TTS generování nespustilo, protože se obsah nezměnil
        mock_submit.assert_not_called()

        # Reset mocku
        mock_submit.reset_mock()

        # 3. Změna obsahu a uložení
        article.content = "Nový obsah článku."
        article.save()

        # Ověření, že se generování TTS spustilo, protože se změnil hash obsahu
        mock_submit.assert_called_once_with(article.__class__._generate_audio, article.pk)
