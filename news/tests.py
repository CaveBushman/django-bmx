from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django_ckeditor_5.widgets import CKEditor5Widget
from .admin import DownloadsAdminForm, NewsAdminForm
from .models import Downloads, News, _generate_audio
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
        with self.captureOnCommitCallbacks(execute=True):
            article = News.objects.create(
                title="Testovací článek pro slug",
                content="Nějaký obsah.",
                published=True
            )

        # Ověření, že se vygeneroval slug
        self.assertEqual(article.slug, "testovaci-clanek-pro-slug")

        # Ověření, že se při prvním uložení zaplánovalo generování TTS
        mock_submit.assert_called_once_with(_generate_audio, article.pk)

        # Reset mocku
        mock_submit.reset_mock()

        # 2. Uložení článku bez změny obsahu
        article.on_homepage = True
        with self.captureOnCommitCallbacks(execute=True):
            article.save()

        # Ověření, že se TTS generování znovu spustilo, protože článek zatím nemá audio soubor
        mock_submit.assert_called_once_with(_generate_audio, article.pk)

        # Reset mocku
        mock_submit.reset_mock()

        # 3. Změna obsahu a uložení
        article.content = "Nový obsah článku."
        with self.captureOnCommitCallbacks(execute=True):
            article.save()

        # Ověření, že se generování TTS spustilo, protože se změnil hash obsahu
        mock_submit.assert_called_once_with(_generate_audio, article.pk)

    @patch('news.models._EXECUTOR.submit')
    def test_get_absolute_url_uses_slug(self, mock_submit):
        article = News.objects.create(
            title="Clanek se slugem",
            content="Obsah",
            published=True,
        )

        self.assertEqual(
            article.get_absolute_url(),
            reverse("news:news-detail", kwargs={"slug": article.slug}),
        )


class NewsDetailCanonicalUrlTests(TestCase):
    @patch('news.models._EXECUTOR.submit')
    def test_numeric_legacy_url_redirects_to_slug(self, mock_submit):
        article = News.objects.create(
            title="Stary odkaz",
            content="Obsah",
            published=True,
        )

        response = self.client.get(
            reverse("news:news-detail", kwargs={"slug": str(article.pk)})
        )

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers["Location"], article.get_absolute_url())


class NewsAdminFormTests(TestCase):
    def test_news_admin_form_uses_ckeditor5_widgets(self):
        form = NewsAdminForm()

        self.assertIsInstance(form.fields["prefix"].widget, CKEditor5Widget)
        self.assertIsInstance(form.fields["content"].widget, CKEditor5Widget)

    def test_downloads_admin_form_uses_ckeditor5_widget(self):
        form = DownloadsAdminForm()

        self.assertIsInstance(form.fields["description"].widget, CKEditor5Widget)


class RichTextSanitizationTests(TestCase):
    @patch('news.models._EXECUTOR.submit')
    def test_news_save_sanitizes_dangerous_html_but_keeps_safe_link(self, mock_submit):
        article = News.objects.create(
            title="Sanitized article",
            prefix='<p>Ok</p><script>alert(1)</script><a href="javascript:alert(1)">bad</a>',
            content='<p>Video <a href="https://www.youtube.com/watch?v=abc" target="_blank">YouTube</a></p>',
            published=False,
        )

        self.assertNotIn("<script", article.prefix)
        self.assertNotIn("javascript:", article.prefix)
        self.assertIn('href="https://www.youtube.com/watch?v=abc"', article.content)
        self.assertIn('rel="noopener noreferrer"', article.content)

    def test_downloads_save_keeps_image_and_removes_unsafe_attributes(self):
        document = Downloads.objects.create(
            title="Document",
            description='<figure class="image"><img src="/media/proposition_uploads/test.png" onerror="alert(1)" alt="Poster"></figure>',
            published=True,
        )

        self.assertIn('src="/media/proposition_uploads/test.png"', document.description)
        self.assertIn('alt="Poster"', document.description)
        self.assertNotIn("onerror", document.description)
