from unittest.mock import patch
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse


class HealthEndpointTests(TestCase):
    def test_healthz_returns_ok(self):
        response = self.client.get(reverse("healthz"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_readyz_returns_readiness_checks(self):
        response = self.client.get(reverse("readyz"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["checks"]["database"]["status"], "ok")
        self.assertEqual(payload["checks"]["cache"]["status"], "ok")

    @patch("bmx.health.check_cache", side_effect=RuntimeError("cache unavailable"))
    def test_readyz_returns_503_when_a_check_fails(self, _check_cache_mock):
        response = self.client.get(reverse("readyz"))

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["checks"]["database"]["status"], "ok")
        self.assertEqual(payload["checks"]["cache"]["status"], "error")
        self.assertIn("cache unavailable", payload["checks"]["cache"]["error"])


class SecurityEndpointTests(TestCase):
    @override_settings(CSP_REPORT_RATE_LIMIT_MAX_ATTEMPTS=1, CSP_REPORT_RATE_LIMIT_WINDOW_SECONDS=60)
    @patch("bmx.views.logger.info")
    def test_csp_report_endpoint_rate_limits_repeated_reports(self, logger_info_mock):
        url = reverse("csp-report")
        body = '{"csp-report":{"blocked-uri":"inline"}}'

        first_response = self.client.post(
            url,
            data=body,
            content_type="application/csp-report",
            REMOTE_ADDR="203.0.113.10",
        )
        second_response = self.client.post(
            url,
            data=body,
            content_type="application/csp-report",
            REMOTE_ADDR="203.0.113.10",
        )

        self.assertEqual(first_response.status_code, 204)
        self.assertEqual(second_response.status_code, 204)
        self.assertEqual(logger_info_mock.call_count, 1)

    @override_settings(CSP_REPORT_MAX_BODY_BYTES=32)
    @patch("bmx.views.logger.info")
    def test_csp_report_endpoint_drops_oversized_payload(self, logger_info_mock):
        response = self.client.post(
            reverse("csp-report"),
            data='{"csp-report":{"blocked-uri":"https://example.com/too-large"}}',
            content_type="application/csp-report",
            REMOTE_ADDR="203.0.113.11",
        )

        self.assertEqual(response.status_code, 204)
        logger_info_mock.assert_not_called()

    def test_homepage_base_template_uses_external_base_scripts(self):
        response = self.client.get(reverse("news:homepage"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "js/base-head.js")
        self.assertContains(response, "js/base.js")
        self.assertContains(response, "js/navbar.js")
        self.assertContains(response, "css/navbar.css")
        self.assertNotContains(response, "document.querySelectorAll(\"[data-flash-message]\")")
        self.assertNotContains(response, "function closeDropdown()")
        self.assertNotContains(response, 'onclick="toggleTheme()"')
        self.assertContains(response, "data-theme-toggle")
        self.assertContains(response, 'id="language-menu-button"')
        self.assertContains(response, 'id="language-menu"')

    def test_navbar_template_uses_external_stylesheet_and_no_inline_style(self):
        template = (
            Path(settings.BASE_DIR) / "theme" / "templates" / "includes" / "navbar.html"
        ).read_text(encoding="utf-8")

        self.assertNotIn("<style>", template)
        self.assertIn("navbar-cart-icon", template)


class LanguageSelectorTests(TestCase):
    """Integration tests for language selector functionality."""

    def test_homepage_contains_language_menu_button(self):
        """Test that homepage renders language menu button."""
        response = self.client.get(reverse("news:homepage"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="language-menu-button"')
        self.assertContains(response, 'id="language-menu"')
        # Check that set_language endpoint exists
        self.assertContains(response, 'action="/i18n/setlang/"')
