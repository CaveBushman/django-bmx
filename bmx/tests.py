from datetime import date, timedelta
from io import BytesIO
from types import SimpleNamespace
import gzip
import sqlite3
import tempfile
from unittest.mock import patch
from pathlib import Path
from decimal import Decimal
import logging
import json

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
import pandas as pd

from bmx import cron as bmx_cron
from bmx.context_processors import navbar_context
from bmx import views as bmx_views
from club.models import Club
from accounts.models import AvatarChangeRequest
from event.models import EntryClasses, Event, EventProposition
from finance.models import EventCashReceipt, EventInvoice
from news.models import News
from rider.models import Rider


User = get_user_model()


class HealthEndpointTests(TestCase):
    def test_healthz_returns_ok(self):
        response = self.client.get(reverse("healthz"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    @patch("bmx.health.check_celery", return_value={"status": "ok", "mode": "eager"})
    def test_readyz_returns_readiness_checks(self, _check_celery_mock):
        response = self.client.get(reverse("readyz"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["checks"]["database"]["status"], "ok")
        self.assertEqual(payload["checks"]["cache"]["status"], "ok")
        self.assertEqual(payload["checks"]["celery"]["status"], "ok")

    @patch("bmx.health.check_celery", return_value={"status": "ok", "mode": "eager"})
    @patch("bmx.health.check_cache", side_effect=RuntimeError("cache unavailable"))
    def test_readyz_returns_503_when_a_check_fails(self, _check_cache_mock, _check_celery_mock):
        response = self.client.get(reverse("readyz"))

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["checks"]["database"]["status"], "ok")
        self.assertEqual(payload["checks"]["cache"]["status"], "error")
        self.assertIn("cache unavailable", payload["checks"]["cache"]["error"])

    @patch("bmx.health.check_celery", side_effect=RuntimeError("No Celery worker responded to ping."))
    def test_readyz_returns_503_when_celery_worker_is_down(self, _check_celery_mock):
        response = self.client.get(reverse("readyz"))

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["checks"]["celery"]["status"], "error")
        self.assertIn("No Celery worker", payload["checks"]["celery"]["error"])


class SitemapEndpointTests(TestCase):
    @override_settings(YOUR_DOMAIN="https://czechbmx.cz")
    def test_legacy_detailxmlk_redirects_to_current_sitemap(self):
        response = self.client.get("/detailxmlk.xml")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://czechbmx.cz/sitemap.xml")


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

    def test_request_id_header_is_preserved_in_response(self):
        response = self.client.get(
            reverse("news:homepage"),
            HTTP_X_REQUEST_ID="req-123",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Request-ID"], "req-123")


class ErrorPageTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(DEBUG=False)
    def test_custom_404_page_is_rendered_for_unknown_route(self):
        response = self.client.get("/this-page-does-not-exist/")

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Stránka nebyla nalezena", status_code=404)

    def test_error_handlers_render_standalone_templates_without_base_dependencies(self):
        request = self.factory.get("/error-page-test/")
        responses = (
            bmx_views.error_400_view(request, Exception("bad request")),
            bmx_views.error_403_view(request, Exception("forbidden")),
            bmx_views.error_404_view(request, Exception("not found")),
            bmx_views.error_500_view(request),
        )

        for response, expected_status in zip(responses, (400, 403, 404, 500)):
            with self.subTest(status=expected_status):
                content = response.content.decode("utf-8")
                self.assertEqual(response.status_code, expected_status)
                self.assertIn("<!DOCTYPE html>", content)
                self.assertNotIn("includes/navbar.html", content)
                self.assertNotIn("js/base.js", content)
                self.assertNotIn("css/navbar.css", content)

    @override_settings(DEBUG=False, ROOT_URLCONF="bmx.test_urls")
    def test_permission_denied_uses_custom_403_page(self):
        response = self.client.get("/__test__/permission-denied/")

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Přístup byl zamítnut", status_code=403)

    @override_settings(DEBUG=False, ROOT_URLCONF="bmx.test_urls")
    def test_runtime_exception_uses_custom_500_page(self):
        self.client.raise_request_exception = False

        response = self.client.get("/__test__/runtime-error/")

        self.assertEqual(response.status_code, 500)
        self.assertContains(response, "Na serveru došlo k chybě", status_code=500)

    @override_settings(DEBUG=False, ROOT_URLCONF="bmx.test_urls")
    def test_csrf_failure_uses_custom_403_page(self):
        csrf_client = Client(enforce_csrf_checks=True)

        response = csrf_client.post("/__test__/csrf-protected/", {})

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Přístup byl zamítnut", status_code=403)
        self.assertContains(response, "bezpečnostní kontroly", status_code=403)


class ContextProcessorResilienceTests(TestCase):
    @patch("accounts.models.AvatarChangeRequest.expire_stale_requests", side_effect=DatabaseError("db down"))
    def test_navbar_context_falls_back_when_database_query_fails(self, _expire_mock):
        request = RequestFactory().get("/")
        user = User.objects.create_user(
            first_name="Context",
            last_name="User",
            username="context_user",
            email="context@example.com",
            password="StrongPass123!",
        )
        user.is_active = True
        user.is_staff = True
        user.save()
        request.user = user
        request.user.credit = 125

        context = navbar_context(request)

        self.assertEqual(context["user_credit"], 125)
        self.assertIn("navbar_eshop_visible", context)


class SecurityFlowTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(team_name="Security Club", is_active=True)
        self.event = Event.objects.create(
            name="Security Event",
            date=date.today() + timedelta(days=10),
            organizer=self.club,
            type_for_ranking="Volný závod",
        )
        self.user = User.objects.create_user(
            first_name="Security",
            last_name="User",
            username="security_user",
            email="security_user@example.com",
            password="StrongPass123!",
        )
        self.user.is_active = True
        self.user.save()
        self.staff_user = User.objects.create_user(
            first_name="Security",
            last_name="Staff",
            username="security_staff",
            email="security_staff@example.com",
            password="StrongPass123!",
        )
        self.staff_user.is_active = True
        self.staff_user.is_staff = True
        self.staff_user.save()

    def test_anonymous_access_to_protected_pages_redirects_instead_of_failing(self):
        responses = (
            self.client.get(reverse("event:credit")),
            self.client.get(reverse("event:event-admin", kwargs={"pk": self.event.pk})),
        )

        for response in responses:
            self.assertEqual(response.status_code, 302)

    def test_invalid_credit_post_returns_form_feedback_without_500(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("event:credit"),
            {"price": "invalid"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Neplatná částka.")

    def test_nonexistent_public_detail_returns_404(self):
        response = self.client.get(reverse("event:event-detail", kwargs={"pk": 999999}))

        self.assertEqual(response.status_code, 404)

    def test_export_results_missing_event_returns_404_error_page(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("event:export_event_results", kwargs={"event_id": 999999}))

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Závod nebyl nalezen.", status_code=404)

    @patch("event.views.views_admin.get_api_token", return_value=None)
    def test_export_results_missing_api_token_returns_502_error_page(self, _token_mock):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("event:export_event_results", kwargs={"event_id": self.event.pk}))

        self.assertEqual(response.status_code, 502)
        self.assertContains(
            response,
            "Nepodařilo se získat token pro přihlášení k API ČSC.",
            status_code=502,
        )


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


class SettingsSecuritySourceTests(TestCase):
    def test_settings_source_contains_explicit_security_toggles(self):
        source = (
            Path(settings.BASE_DIR) / "bmx" / "settings.py"
        ).read_text(encoding="utf-8")

        self.assertIn('CSP_ENFORCE = config_bool("CSP_ENFORCE"', source)
        self.assertIn('ENABLE_HTTPS_SECURITY = config_bool("ENABLE_HTTPS_SECURITY"', source)
        self.assertIn('CSRF_TRUSTED_ORIGINS = config_list(', source)
        self.assertIn('SECURE_SSL_REDIRECT = config_bool("SECURE_SSL_REDIRECT", default=not DEBUG)', source)
        self.assertNotIn('SECURE_SSL_REDIRECT = config_bool("SECURE_SSL_REDIRECT", default=STRIPE_LIVE_MODE)', source)

    def test_settings_source_contains_separated_stripe_key_loading(self):
        source = (
            Path(settings.BASE_DIR) / "bmx" / "settings.py"
        ).read_text(encoding="utf-8")

        self.assertIn('STRIPE_LIVE_PUBLIC_KEY', source)
        self.assertIn('STRIPE_LIVE_SECRET_KEY', source)
        self.assertIn('STRIPE_TEST_PUBLIC_KEY', source)
        self.assertIn('STRIPE_TEST_SECRET_KEY', source)
        self.assertIn('STRIPE_LIVE_ENDPOINT_SECRET', source)
        self.assertIn('STRIPE_TEST_ENDPOINT_SECRET', source)
        self.assertIn('config_first(["STRIPE_LIVE_PUBLIC_KEY", "STRIPE_PUBLIC_KEY"])', source)

    def test_settings_source_contains_sentry_configuration_toggles(self):
        source = (
            Path(settings.BASE_DIR) / "bmx" / "settings.py"
        ).read_text(encoding="utf-8")

        self.assertIn('SENTRY_DSN = config("SENTRY_DSN", default="")', source)
        self.assertIn('SENTRY_ENABLED = config_bool("SENTRY_ENABLED", default=not DEBUG)', source)
        self.assertIn('SENTRY_SEND_DEFAULT_PII = config_bool("SENTRY_SEND_DEFAULT_PII", default=False)', source)
        self.assertIn('SENTRY_MAX_BREADCRUMBS = config("SENTRY_MAX_BREADCRUMBS", default=50, cast=int)', source)
        self.assertIn('LOG_AS_JSON = config_bool("LOG_AS_JSON", default=not DEBUG)', source)
        self.assertIn('initialize_sentry(', source)

    def test_settings_source_keeps_production_cache_warning_out_of_tests(self):
        source = (
            Path(settings.BASE_DIR) / "bmx" / "settings.py"
        ).read_text(encoding="utf-8")
        env_example = (
            Path(settings.BASE_DIR) / "bmx" / ".env.example"
        ).read_text(encoding="utf-8")

        self.assertIn("RUNNING_TESTS =", source)
        self.assertIn("SUPPRESS_LOCMEM_CACHE_WARNING_COMMANDS", source)
        self.assertIn("ALLOW_LOCMEM_CACHE_IN_PRODUCTION", source)
        self.assertIn("not SUPPRESS_LOCMEM_CACHE_WARNING", source)
        self.assertIn("LocMemCache nezajišťuje sdílené rate limity", source)
        self.assertIn("REDIS_URL=redis://127.0.0.1:6379/1", env_example)
        self.assertIn("ALLOW_LOCMEM_CACHE_IN_PRODUCTION=false", env_example)

    def test_static_build_source_of_truth_is_documented(self):
        settings_source = (
            Path(settings.BASE_DIR) / "bmx" / "settings.py"
        ).read_text(encoding="utf-8")
        makefile = (Path(settings.BASE_DIR) / "Makefile").read_text(encoding="utf-8")
        tailwind_source = (
            Path(settings.BASE_DIR) / "theme" / "static_src" / "src" / "styles.css"
        ).read_text(encoding="utf-8")
        package_json = (
            Path(settings.BASE_DIR) / "theme" / "static_src" / "package.json"
        ).read_text(encoding="utf-8")

        self.assertIn('TAILWIND_APP_NAME = "theme"', settings_source)
        self.assertIn('TAILWIND_CSS_PATH = "css/dist/styles.css"', settings_source)
        self.assertIn("npm run build --prefix theme/static_src", makefile)
        self.assertIn('@source "../../../**/*.html";', tailwind_source)
        self.assertIn('"build:tailwind": "tailwindcss -i ./src/styles.css -o ../static/css/dist/styles.css --minify"', package_json)

    def test_observability_helper_falls_back_without_sentry_sdk(self):
        from bmx.observability import start_span

        with patch("bmx.observability.sentry_sdk", None):
            with start_span(op="test", name="fallback-span"):
                pass

    def test_scrub_sentry_event_filters_sensitive_request_values(self):
        from bmx.observability import scrub_sentry_event

        scrubbed = scrub_sentry_event(
            {
                "request": {
                    "url": "https://example.com/checkout?token=secret&ok=1",
                    "headers": {
                        "Authorization": "Bearer secret",
                        "X-Test": "value",
                    },
                    "data": {
                        "password": "secret",
                        "safe": "value",
                    },
                    "cookies": {"sessionid": "secret"},
                },
                "user": {
                    "id": 1,
                    "email": "user@example.com",
                    "username": "tester",
                },
            }
        )

        self.assertEqual(scrubbed["request"]["headers"]["Authorization"], "[Filtered]")
        self.assertEqual(scrubbed["request"]["headers"]["X-Test"], "value")
        self.assertEqual(scrubbed["request"]["data"]["password"], "[Filtered]")
        self.assertEqual(scrubbed["request"]["data"]["safe"], "value")
        self.assertEqual(scrubbed["request"]["cookies"], "[Filtered]")
        self.assertIn("token=%5BFiltered%5D", scrubbed["request"]["url"])
        self.assertNotIn("email", scrubbed["user"])
        self.assertNotIn("username", scrubbed["user"])

    def test_sentry_traces_sampler_skips_healthchecks(self):
        from bmx.observability import sentry_traces_sampler

        sample_rate = sentry_traces_sampler(
            {
                "transaction_context": {"name": "/healthz"},
                "wsgi_environ": {"PATH_INFO": "/healthz"},
            },
            traces_sample_rate=0.5,
            healthcheck_paths={"/healthz"},
        )

        self.assertEqual(sample_rate, 0.0)

    def test_initialize_sentry_passes_expected_options(self):
        from bmx.observability import initialize_sentry

        init_mock = SimpleNamespace()
        configure_scope_calls = []

        class Scope:
            def __init__(self):
                self.tags = {}

            def set_tag(self, key, value):
                self.tags[key] = value

        class ScopeContext:
            def __enter__(self_inner):
                scope = Scope()
                configure_scope_calls.append(scope)
                return scope

            def __exit__(self_inner, exc_type, exc, tb):
                return False

        def fake_logging_integration(*, level, event_level):
            return {
                "level": level,
                "event_level": event_level,
            }

        def fake_init(**kwargs):
            init_mock.kwargs = kwargs

        fake_sdk = SimpleNamespace(
            init=fake_init,
            configure_scope=lambda: ScopeContext(),
        )

        with patch("bmx.observability.sentry_sdk", fake_sdk), patch(
            "bmx.observability.DjangoIntegration",
            side_effect=lambda: "django-integration",
        ), patch(
            "bmx.observability.LoggingIntegration",
            side_effect=fake_logging_integration,
        ):
            initialized = initialize_sentry(
                dsn="https://examplePublicKey@o0.ingest.sentry.io/0",
                enabled=True,
                environment="production",
                release="abc123",
                traces_sample_rate=0.25,
                profiles_sample_rate=0.1,
                send_default_pii=False,
                max_breadcrumbs=75,
                log_level=logging.INFO,
                event_level=logging.ERROR,
                healthcheck_paths={"/healthz"},
                debug=False,
                stripe_live_mode=True,
            )

        self.assertTrue(initialized)
        self.assertEqual(init_mock.kwargs["dsn"], "https://examplePublicKey@o0.ingest.sentry.io/0")
        self.assertEqual(init_mock.kwargs["environment"], "production")
        self.assertEqual(init_mock.kwargs["release"], "abc123")
        self.assertEqual(init_mock.kwargs["max_request_body_size"], "never")
        self.assertEqual(init_mock.kwargs["max_breadcrumbs"], 75)
        self.assertEqual(init_mock.kwargs["profiles_sample_rate"], 0.1)
        self.assertIn("django-integration", init_mock.kwargs["integrations"])
        self.assertIn(
            {"level": logging.INFO, "event_level": logging.ERROR},
            init_mock.kwargs["integrations"],
        )
        self.assertEqual(configure_scope_calls[0].tags["app"], "django-bmx")
        self.assertTrue(configure_scope_calls[0].tags["stripe.live_mode"])

    def test_json_formatter_includes_release_and_environment(self):
        from bmx.logging_config import JsonFormatter

        formatter = JsonFormatter(release="release-1", environment="production")
        record = logging.LogRecord(
            name="bmx.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello world",
            args=(),
            exc_info=None,
        )

        payload = json.loads(formatter.format(record))

        self.assertEqual(payload["logger"], "bmx.test")
        self.assertEqual(payload["message"], "hello world")
        self.assertEqual(payload["release"], "release-1")
        self.assertEqual(payload["environment"], "production")
        self.assertEqual(payload["request_id"], "-")

    def test_env_example_exists_with_sentry_and_logging_placeholders(self):
        source = (
            Path(settings.BASE_DIR) / "bmx" / ".env.example"
        ).read_text(encoding="utf-8")

        self.assertIn("SECRET_KEY=replace-with-strong-secret", source)
        self.assertIn("SENTRY_DSN=https://examplePublicKey@o0.ingest.sentry.io/0", source)
        self.assertIn("LOG_AS_JSON=true", source)

    def test_entry_views_source_contains_custom_performance_spans(self):
        source = (
            Path(settings.BASE_DIR) / "event" / "views" / "views_entry.py"
        ).read_text(encoding="utf-8")

        self.assertIn("from bmx.observability import set_tag, start_span", source)
        self.assertIn('name="create_entry_checkout_session"', source)
        self.assertIn('name="generate_event_invoices"', source)
        self.assertIn('name="export_cash_receipts_xml"', source)

    def test_observability_sources_contain_tags_and_service_spans(self):
        payment_helper_source = (
            Path(settings.BASE_DIR) / "event" / "views" / "payment_helpers.py"
        ).read_text(encoding="utf-8")
        invoice_source = (
            Path(settings.BASE_DIR) / "finance" / "invoices.py"
        ).read_text(encoding="utf-8")
        cash_receipt_source = (
            Path(settings.BASE_DIR) / "finance" / "cash_receipts.py"
        ).read_text(encoding="utf-8")

        self.assertIn('set_tag("stripe.session_id"', payment_helper_source)
        self.assertIn('name="credit_webhook_credit_transaction_lookup"', payment_helper_source)
        self.assertIn('name="generate_invoice_pdf"', invoice_source)
        self.assertIn('name="save_invoice_files"', invoice_source)
        self.assertIn('name="generate_cash_receipt_pdf"', cash_receipt_source)
        self.assertIn('name="build_cash_receipts_xml"', cash_receipt_source)


class PublicPageSmokeTests(TestCase):
    """Smoke tests to catch unexpected 500 errors on core public pages."""

    def test_core_public_pages_do_not_return_500(self):
        urls = (
            reverse("news:homepage"),
            reverse("news:news-list"),
            reverse("event:events"),
            reverse("rider:list"),
            reverse("club:clubs-list"),
            reverse("ranking:ranking"),
            reverse("news:rules"),
            reverse("news:downloads"),
        )

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertNotEqual(
                    response.status_code,
                    500,
                    msg=f"{url} returned HTTP 500",
                )
                self.assertLess(
                    response.status_code,
                    600,
                    msg=f"{url} returned unexpected 5xx status {response.status_code}",
                )


class PublicDetailPageSmokeTests(TestCase):
    def setUp(self):
        self.generate_audio_patcher = patch("news.tasks.generate_audio_task.delay")
        self.translate_article_patcher = patch("news.tasks.translate_article_task.delay")
        self.generate_audio_patcher.start()
        self.translate_article_patcher.start()
        self.addCleanup(self.generate_audio_patcher.stop)
        self.addCleanup(self.translate_article_patcher.stop)

        self.club = Club.objects.create(team_name="Smoke Club", is_active=True)
        self.entry_classes = EntryClasses.objects.create(
            event_name="Smoke classes",
            boys_6="Boys 6",
            girls_6="Girls 6",
            cr_boys_12_and_under="Boys 12 and under",
            beginners_1="Beginners 1",
        )
        self.event = Event.objects.create(
            name="Smoke Event",
            date=date.today() + timedelta(days=14),
            organizer=self.club,
            classes_and_fees_like=self.entry_classes,
            reg_open=True,
            reg_open_from=timezone.now() - timedelta(days=1),
            reg_open_to=timezone.now() + timedelta(days=7),
            type_for_ranking="Volný závod",
        )
        self.rider = Rider.objects.create(
            uci_id=12345670001,
            first_name="Smoke",
            last_name="Rider",
            gender="Muž",
            date_of_birth=date(2012, 1, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            class_20="Boys 6",
            class_24="Boys 12 and under",
            class_beginner="Beginners 1",
        )
        with self.captureOnCommitCallbacks(execute=True):
            self.article = News.objects.create(
                title="Smoke Article",
                content="Smoke content",
                published=True,
            )

    def test_core_detail_pages_do_not_return_500(self):
        urls = (
            self.article.get_absolute_url(),
            reverse("event:event-detail", kwargs={"pk": self.event.pk}),
            reverse("event:entry-riders", kwargs={"pk": self.event.pk}),
            reverse("club:club-detail", kwargs={"pk": self.club.pk}),
            reverse("rider:detail", kwargs={"pk": self.rider.uci_id}),
        )

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertNotEqual(
                    response.status_code,
                    500,
                    msg=f"{url} returned HTTP 500",
                )
                self.assertLess(
                    response.status_code,
                    600,
                    msg=f"{url} returned unexpected 5xx status {response.status_code}",
                )

    def test_homepage_for_authenticated_user_does_not_return_500(self):
        user = User.objects.create_user(
            first_name="Smoke",
            last_name="User",
            username="smoke_user",
            email="smoke_user@example.com",
            password="StrongPass123!",
        )
        user.is_active = True
        user.save()
        self.client.force_login(user)

        response = self.client.get(reverse("news:homepage"))

        self.assertEqual(response.status_code, 200)


class InternalPageSmokeTests(TestCase):
    def setUp(self):
        self.temp_media_dir = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.temp_media_dir.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.temp_media_dir.cleanup)

        self.staff_user = User.objects.create_user(
            first_name="Internal",
            last_name="Staff",
            username="internal_staff",
            email="internal_staff@example.com",
            password="StrongPass123!",
        )
        self.staff_user.is_active = True
        self.staff_user.is_staff = True
        self.staff_user.save()

        self.club = Club.objects.create(team_name="Internal Smoke Club", is_active=True)
        self.entry_classes = EntryClasses.objects.create(
            event_name="Internal smoke classes",
            boys_6="Boys 6",
            girls_6="Girls 6",
            cr_boys_12_and_under="Boys 12 and under",
            beginners_1="Beginners 1",
        )
        self.event = Event.objects.create(
            name="Internal Smoke Event",
            date=date.today() + timedelta(days=21),
            organizer=self.club,
            classes_and_fees_like=self.entry_classes,
            reg_open=False,
            reg_open_from=timezone.now() - timedelta(days=2),
            reg_open_to=timezone.now() + timedelta(days=2),
            type_for_ranking="Volný závod",
        )

    def test_internal_pages_do_not_return_500_for_staff(self):
        self.client.force_login(self.staff_user)
        urls = (
            reverse("event:event-admin", kwargs={"pk": self.event.pk}),
            reverse("event:fees-on-event", kwargs={"pk": self.event.pk}),
            reverse("event:commissar-assignments"),
            reverse("event:credit"),
            reverse("user:account"),
            reverse("user:trainer-dashboard"),
        )

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertNotEqual(
                    response.status_code,
                    500,
                    msg=f"{url} returned HTTP 500",
                )
                self.assertLess(
                    response.status_code,
                    600,
                    msg=f"{url} returned unexpected 5xx status {response.status_code}",
                )

    def test_proposition_edit_post_does_not_return_500_for_staff(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("event:proposition-edit", kwargs={"pk": self.event.pk}),
            {
                "venue_name": "BMX Track",
                "venue_address": "Test Street 1",
                "office_hours": "08:00-16:00",
                "contact_name": "Race Office",
                "contact_email": "office@example.com",
                "contact_phone": "777123456",
                "summary": "<p>Summary</p>",
                "schedule": "<p>Schedule</p>",
                "categories": "<p>Categories</p>",
                "registration_info": "<p>Registration</p>",
                "awards": "<p>Awards</p>",
                "accommodation": "<p>Accommodation</p>",
                "additional_info": "<p>Additional info</p>",
                "is_published": "on",
            },
        )

        self.assertNotEqual(response.status_code, 500)
        self.assertLess(response.status_code, 600)
        self.assertTrue(
            EventProposition.objects.filter(event=self.event, is_published=True).exists()
        )

    def test_credit_post_with_invalid_amount_does_not_return_500(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("event:credit"),
            {"price": "invalid"},
        )

        self.assertNotEqual(response.status_code, 500)
        self.assertLess(response.status_code, 600)

    @patch("event.views.views_entry.send_event_invoices")
    @patch("event.views.views_entry.generate_event_invoices")
    def test_fees_on_event_post_actions_do_not_return_500(
        self,
        generate_event_invoices_mock,
        send_event_invoices_mock,
    ):
        self.client.force_login(self.staff_user)
        generate_event_invoices_mock.return_value = {"generated": []}
        send_event_invoices_mock.return_value = {"generated": [], "sent": [], "skipped": []}

        responses = (
            self.client.post(
                reverse("event:fees-on-event", kwargs={"pk": self.event.pk}),
                {"btn-generate-invoices": "1"},
            ),
            self.client.post(
                reverse("event:fees-on-event", kwargs={"pk": self.event.pk}),
                {"btn-send-invoices": "1"},
            ),
        )

        for response in responses:
            self.assertNotEqual(response.status_code, 500)
            self.assertLess(response.status_code, 600)

    @patch("event.views.views_admin.trigger_cn_qualification_recount_if_needed")
    @patch("event.views.views_admin.schedule_ranking_recount")
    @patch("event.views.views_admin.pd.read_excel")
    @patch("event.views.views_admin._save_uploaded_file")
    def test_event_admin_xls_upload_does_not_return_500(
        self,
        save_uploaded_file_mock,
        read_excel_mock,
        schedule_ranking_recount_mock,
        trigger_cn_recount_mock,
    ):
        self.client.force_login(self.staff_user)
        fake_storage = SimpleNamespace(path=lambda filename: f"/tmp/{filename}")
        save_uploaded_file_mock.return_value = (
            fake_storage,
            "results.xlsx",
            "xls_results/results.xlsx",
        )
        read_excel_mock.return_value = pd.DataFrame([{"placeholder": 1}])

        response = self.client.post(
            reverse("event:event-admin", kwargs={"pk": self.event.pk}),
            {
                "btn-upload-result": "1",
                "result-file": SimpleUploadedFile(
                    "results.xlsx",
                    b"fake-xlsx-content",
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )

        self.assertNotEqual(response.status_code, 500)
        self.assertLess(response.status_code, 600)
        schedule_ranking_recount_mock.assert_called_once()
        trigger_cn_recount_mock.assert_called_once_with(self.event)

    @patch("event.views.views_admin.SetResults")
    @patch("event.views.views_admin._save_uploaded_file")
    def test_event_admin_txt_upload_does_not_return_500(
        self,
        save_uploaded_file_mock,
        set_results_mock,
    ):
        self.client.force_login(self.staff_user)
        fake_storage = SimpleNamespace(path=lambda filename: f"/tmp/{filename}")
        save_uploaded_file_mock.return_value = (
            fake_storage,
            "results.txt",
            "rem_results/results.txt",
        )

        response = self.client.post(
            reverse("event:event-admin", kwargs={"pk": self.event.pk}),
            {
                "btn-upload-txt": "1",
                "result-file-txt": SimpleUploadedFile(
                    "results.txt",
                    b"fake-rem-results",
                    content_type="text/plain",
                ),
            },
        )

        self.assertNotEqual(response.status_code, 500)
        self.assertLess(response.status_code, 600)
        set_results_mock.assert_called_once()


class AuthorizationBoundaryTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(team_name="Home Club", is_active=True)
        self.other_club = Club.objects.create(team_name="Other Club", is_active=True)
        self.event = Event.objects.create(
            name="Boundary Event",
            date=date.today() + timedelta(days=10),
            organizer=self.club,
            type_for_ranking="Volný závod",
            reg_open=False,
        )
        self.other_event = Event.objects.create(
            name="Other Boundary Event",
            date=date.today() + timedelta(days=11),
            organizer=self.other_club,
            type_for_ranking="Volný závod",
            reg_open=False,
        )

        self.home_manager = User.objects.create_user(
            first_name="Home",
            last_name="Manager",
            username="home_manager",
            email="home_manager@example.com",
            password="StrongPass123!",
        )
        self.home_manager.is_active = True
        self.home_manager.is_club_manager = True
        self.home_manager.club = self.club
        self.home_manager.save(update_fields=["is_active", "is_club_manager", "club"])

        self.other_manager = User.objects.create_user(
            first_name="Other",
            last_name="Manager",
            username="other_manager",
            email="other_manager@example.com",
            password="StrongPass123!",
        )
        self.other_manager.is_active = True
        self.other_manager.is_club_manager = True
        self.other_manager.club = self.other_club
        self.other_manager.save(update_fields=["is_active", "is_club_manager", "club"])

        self.staff_user = User.objects.create_user(
            first_name="Staff",
            last_name="Only",
            username="staff_only",
            email="staff_only@example.com",
            password="StrongPass123!",
        )
        self.staff_user.is_active = True
        self.staff_user.is_staff = True
        self.staff_user.save(update_fields=["is_active", "is_staff"])

        self.finance_admin = User.objects.create_user(
            first_name="Finance",
            last_name="Admin",
            username="finance_admin",
            email="finance_admin@example.com",
            password="StrongPass123!",
        )
        self.finance_admin.is_active = True
        self.finance_admin.is_admin = True
        self.finance_admin.save(update_fields=["is_active", "is_admin"])
        self.receipt = EventCashReceipt.objects.create(
            number="PR-001",
            issue_date=date.today(),
            event=self.other_event,
            rider_name="Other Rider",
            amount=Decimal("250.00"),
        )
        self.invoice = EventInvoice.objects.create(
            number="2026-001",
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=14),
            event=self.other_event,
            club=self.other_club,
            total_price=Decimal("500.00"),
        )

    def test_non_owner_club_manager_cannot_edit_foreign_event_proposition(self):
        self.client.force_login(self.other_manager)

        response = self.client.post(
            reverse("event:proposition-edit", kwargs={"pk": self.event.pk}),
            {
                "venue_name": "Foreign track",
                "summary": "<p>Blocked</p>",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(EventProposition.objects.filter(event=self.event).exists())
        self.assertContains(response, "Propozice může upravovat jen klubový manažer pořadatelského klubu.")

    def test_owner_club_manager_can_edit_event_proposition(self):
        self.client.force_login(self.home_manager)

        response = self.client.post(
            reverse("event:proposition-edit", kwargs={"pk": self.event.pk}),
            {
                "venue_name": "Home track",
                "venue_address": "Street 1",
                "office_hours": "08:00",
                "contact_name": "Office",
                "contact_email": "office@example.com",
                "contact_phone": "777123456",
                "summary": "<p>Allowed</p>",
                "schedule": "<p>Schedule</p>",
                "categories": "<p>Categories</p>",
                "registration_info": "<p>Registration</p>",
                "awards": "<p>Awards</p>",
                "accommodation": "<p>Accommodation</p>",
                "additional_info": "<p>Additional</p>",
                "is_published": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(EventProposition.objects.filter(event=self.event, venue_name="Home track").exists())

    def test_anonymous_user_is_redirected_from_internal_pages(self):
        urls = (
            reverse("event:fees-on-event", kwargs={"pk": self.event.pk}),
            reverse("user:account"),
            reverse("finance:finance"),
        )

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)

    def test_staff_user_cannot_access_finance_dashboard(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("finance:finance"))

        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response.url, reverse("finance:finance"))

    def test_finance_admin_can_access_finance_dashboard(self):
        self.client.force_login(self.finance_admin)

        response = self.client.get(reverse("finance:finance"))

        self.assertEqual(response.status_code, 200)

    def test_staff_user_cannot_access_finance_exports_or_audit_dashboard(self):
        self.client.force_login(self.staff_user)

        for url in (
            reverse("finance:export_checkout_refunds_csv"),
            reverse("finance:finance_audit"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertNotEqual(response.url, url)

    def test_finance_admin_can_access_finance_exports_or_audit_dashboard(self):
        self.client.force_login(self.finance_admin)

        csv_response = self.client.get(reverse("finance:export_checkout_refunds_csv"))
        audit_response = self.client.get(reverse("finance:finance_audit"))

        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(csv_response["Content-Type"], "text/csv; charset=utf-8")
        self.assertEqual(audit_response.status_code, 200)

    def test_avatar_moderation_requires_staff_access(self):
        restricted_users = (None, self.home_manager)

        for user in restricted_users:
            if user is None:
                self.client.logout()
            else:
                self.client.force_login(user)

            response = self.client.get(reverse("accounts:avatar-moderation"))
            self.assertEqual(response.status_code, 302)

        self.client.force_login(self.staff_user)
        allowed_response = self.client.get(reverse("accounts:avatar-moderation"))
        self.assertEqual(allowed_response.status_code, 200)

    def test_non_staff_cannot_post_avatar_moderation_actions(self):
        pending_request = AvatarChangeRequest.objects.create(
            uploaded_by=self.home_manager,
            target_account=self.home_manager,
            image=SimpleUploadedFile("avatar.png", b"fake-avatar", content_type="image/png"),
        )
        self.client.force_login(self.home_manager)

        response = self.client.post(
            reverse("accounts:avatar-moderation"),
            {"action": "approve", "request_id": pending_request.pk},
        )

        pending_request.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(pending_request.status, AvatarChangeRequest.STATUS_PENDING)

    @patch("accounts.models.AvatarChangeRequest.review")
    def test_staff_can_post_avatar_moderation_actions(
        self,
        avatar_review_mock,
    ):
        pending_request = AvatarChangeRequest.objects.create(
            uploaded_by=self.home_manager,
            target_account=self.home_manager,
            image=SimpleUploadedFile("avatar.png", b"fake-avatar", content_type="image/png"),
        )
        avatar_review_mock.return_value = AvatarChangeRequest.STATUS_APPROVED
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("accounts:avatar-moderation"),
            {"action": "approve", "request_id": pending_request.pk},
        )

        self.assertEqual(response.status_code, 302)
        avatar_review_mock.assert_called_once_with("approve", self.staff_user)

    def test_non_staff_cannot_delete_cash_receipts(self):
        owned_receipt = EventCashReceipt.objects.create(
            number="PR-OWN-001",
            issue_date=date.today(),
            event=self.event,
            rider_name="Home Rider",
            amount=Decimal("150.00"),
        )
        self.client.force_login(self.home_manager)

        response = self.client.post(
            reverse("event:cash-receipt-delete", kwargs={"pk": self.event.pk, "receipt_id": owned_receipt.pk})
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(EventCashReceipt.objects.filter(pk=owned_receipt.pk).exists())

    @patch("event.views.views_entry.EventCashReceiptService.export_xml_for_event")
    def test_cash_receipts_export_requires_staff_access(
        self,
        export_xml_mock,
    ):
        export_xml_mock.return_value = b"<cash-receipts />"
        self.client.force_login(self.home_manager)

        blocked_response = self.client.get(
            reverse("event:cash-receipts-export", kwargs={"pk": self.event.pk})
        )

        self.assertEqual(blocked_response.status_code, 302)
        export_xml_mock.assert_not_called()

        self.client.force_login(self.staff_user)
        allowed_response = self.client.get(
            reverse("event:cash-receipts-export", kwargs={"pk": self.event.pk})
        )

        self.assertEqual(allowed_response.status_code, 200)
        self.assertEqual(allowed_response["Content-Type"], "application/xml")
        export_xml_mock.assert_called_once()

    @patch("event.views.views_entry.save_invoice_override")
    def test_non_staff_cannot_post_invoice_edits(
        self,
        save_invoice_override_mock,
    ):
        self.client.force_login(self.home_manager)

        response = self.client.post(
            reverse("event:invoice-edit", kwargs={"pk": self.event.pk, "club_id": self.club.pk}),
            {
                "description": ["Fee item"],
                "amount": ["100.00"],
            },
        )

        self.assertEqual(response.status_code, 302)
        save_invoice_override_mock.assert_not_called()

    def test_cash_receipt_views_do_not_allow_cross_event_object_access(self):
        self.client.force_login(self.staff_user)

        for url in (
            reverse("event:cash-receipt-pdf", kwargs={"pk": self.event.pk, "receipt_id": self.receipt.pk}),
            reverse("event:cash-receipt-edit", kwargs={"pk": self.event.pk, "receipt_id": self.receipt.pk}),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 404)

        delete_response = self.client.post(
            reverse("event:cash-receipt-delete", kwargs={"pk": self.event.pk, "receipt_id": self.receipt.pk})
        )
        self.assertEqual(delete_response.status_code, 404)

    def test_invoice_delete_does_not_allow_cross_event_object_access(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("event:invoice-delete", kwargs={"pk": self.event.pk, "invoice_id": self.invoice.pk})
        )

        self.assertEqual(response.status_code, 404)

    def test_event_admin_upload_actions_without_file_do_not_return_500(self):
        self.client.force_login(self.staff_user)
        responses = (
            self.client.post(
                reverse("event:event-admin", kwargs={"pk": self.event.pk}),
                {"btn-upload-result": "1"},
            ),
            self.client.post(
                reverse("event:event-admin", kwargs={"pk": self.event.pk}),
                {"btn-upload-txt": "1"},
            ),
        )

        for response in responses:
            self.assertNotEqual(response.status_code, 500)
            self.assertLess(response.status_code, 600)

    @patch("event.views.views_admin._handle_rem_riders")
    @patch("event.views.views_admin._handle_rem_entries")
    @patch("event.views.views_admin._handle_bem_riders")
    @patch("event.views.views_admin._handle_bem_entries")
    def test_event_admin_export_actions_do_not_return_500(
        self,
        handle_bem_entries_mock,
        handle_bem_riders_mock,
        handle_rem_entries_mock,
        handle_rem_riders_mock,
    ):
        self.client.force_login(self.staff_user)
        downloadable_path = str(Path(settings.BASE_DIR) / "manage.py")
        handle_bem_entries_mock.return_value = downloadable_path
        handle_bem_riders_mock.return_value = downloadable_path
        handle_rem_entries_mock.return_value = downloadable_path
        handle_rem_riders_mock.return_value = downloadable_path

        responses = (
            self.client.post(
                reverse("event:event-admin", kwargs={"pk": self.event.pk}),
                {"btn-bem-file": "1"},
            ),
            self.client.post(
                reverse("event:event-admin", kwargs={"pk": self.event.pk}),
                {"btn-riders-list": "1"},
            ),
            self.client.post(
                reverse("event:event-admin", kwargs={"pk": self.event.pk}),
                {"btn-rem-file": "1"},
            ),
            self.client.post(
                reverse("event:event-admin", kwargs={"pk": self.event.pk}),
                {"btn-rem-riders-list": "1"},
            ),
        )

        for response in responses:
            self.assertNotEqual(response.status_code, 500)
            self.assertLess(response.status_code, 600)


class BackupCronTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.db_path = Path(self.temp_dir.name) / "db.sqlite3"
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

    def test_gzip_backup_compresses_and_removes_original(self):
        src = Path(self.temp_dir.name) / "db.sqlite3.bak-20260101-000000"
        src.write_bytes(b"hello world")

        gz_path = bmx_cron._gzip_backup(src)

        self.assertEqual(gz_path.name, "db.sqlite3.bak-20260101-000000.gz")
        self.assertFalse(src.exists())
        with gzip.open(gz_path, "rb") as f:
            self.assertEqual(f.read(), b"hello world")

    def test_backup_scheduled_creates_compressed_file_and_skips_offsite_by_default(self):
        db_settings = {**settings.DATABASES["default"], "NAME": str(self.db_path)}
        with override_settings(DATABASES={"default": db_settings}, OFFSITE_BACKUP_RCLONE_REMOTE=""):
            with patch("bmx.cron.subprocess.run", wraps=bmx_cron.subprocess.run) as run_mock:
                bmx_cron.backup_sqlite_scheduled()

        backups = list(Path(self.temp_dir.name).glob("db.sqlite3.bak-*.gz"))
        self.assertEqual(len(backups), 1)
        with gzip.open(backups[0], "rb") as f:
            self.assertEqual(f.read(16)[:6], b"SQLite")

        # rclone never invoked when no offsite remote is configured.
        for call in run_mock.call_args_list:
            self.assertNotEqual(call.args[0][0], "rclone")

    def test_backup_scheduled_uploads_offsite_when_remote_configured(self):
        db_settings = {**settings.DATABASES["default"], "NAME": str(self.db_path)}
        with override_settings(DATABASES={"default": db_settings}, OFFSITE_BACKUP_RCLONE_REMOTE="gdrive:bmx-zalohy"):
            with patch("bmx.cron._upload_backup_offsite") as upload_mock:
                bmx_cron.backup_sqlite_scheduled()

        upload_mock.assert_called_once()
        uploaded_path = upload_mock.call_args[0][0]
        self.assertTrue(uploaded_path.name.startswith("db.sqlite3.bak-"))
        self.assertTrue(uploaded_path.name.endswith(".gz"))

    @override_settings(OFFSITE_BACKUP_RCLONE_REMOTE="")
    def test_upload_offsite_skipped_when_remote_not_configured(self):
        with patch("bmx.cron.subprocess.run") as run_mock:
            bmx_cron._upload_backup_offsite(Path("/tmp/db.sqlite3.bak-20260101-000000.gz"))

        run_mock.assert_not_called()

    @override_settings(OFFSITE_BACKUP_RCLONE_REMOTE="gdrive:bmx-zalohy", OFFSITE_BACKUP_RETENTION_DAYS=30)
    def test_upload_offsite_copies_and_prunes_via_rclone(self):
        backup_path = Path(self.temp_dir.name) / "db.sqlite3.bak-20260101-000000.gz"
        backup_path.write_bytes(b"data")

        with patch(
            "bmx.cron.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
        ) as run_mock:
            bmx_cron._upload_backup_offsite(backup_path)

        self.assertEqual(run_mock.call_count, 2)
        copy_args = run_mock.call_args_list[0].args[0]
        delete_args = run_mock.call_args_list[1].args[0]
        self.assertEqual(copy_args, ["rclone", "copy", str(backup_path), "gdrive:bmx-zalohy", "--quiet"])
        self.assertEqual(delete_args, ["rclone", "delete", "gdrive:bmx-zalohy", "--min-age", "30d", "--quiet"])

    @override_settings(OFFSITE_BACKUP_RCLONE_REMOTE="gdrive:bmx-zalohy")
    def test_upload_offsite_failure_does_not_prune(self):
        with patch(
            "bmx.cron.subprocess.run",
            return_value=SimpleNamespace(returncode=1, stdout="", stderr="auth error"),
        ) as run_mock:
            bmx_cron._upload_backup_offsite(Path("/tmp/db.sqlite3.bak-20260101-000000.gz"))

        run_mock.assert_called_once()

    @override_settings(OFFSITE_BACKUP_RCLONE_REMOTE="gdrive:bmx-zalohy")
    def test_upload_offsite_handles_missing_rclone_gracefully(self):
        with patch("bmx.cron.subprocess.run", side_effect=FileNotFoundError):
            bmx_cron._upload_backup_offsite(Path("/tmp/db.sqlite3.bak-20260101-000000.gz"))

    @override_settings(DATABASES={"default": {**settings.DATABASES["default"], "ENGINE": "django.db.backends.sqlite3"}})
    def test_backup_database_scheduled_dispatches_to_sqlite(self):
        with patch("bmx.cron.backup_sqlite_scheduled") as sqlite_mock, \
                patch("bmx.cron.backup_postgres_scheduled") as postgres_mock:
            bmx_cron.backup_database_scheduled()

        sqlite_mock.assert_called_once()
        postgres_mock.assert_not_called()

    @override_settings(DATABASES={"default": {**settings.DATABASES["default"], "ENGINE": "django.db.backends.postgresql"}})
    def test_backup_database_scheduled_dispatches_to_postgres(self):
        with patch("bmx.cron.backup_sqlite_scheduled") as sqlite_mock, \
                patch("bmx.cron.backup_postgres_scheduled") as postgres_mock:
            bmx_cron.backup_database_scheduled()

        postgres_mock.assert_called_once()
        sqlite_mock.assert_not_called()

    @override_settings(DATABASES={"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "bmx_prod",
        "USER": "bmx",
        "PASSWORD": "secret",
        "HOST": "localhost",
        "PORT": "5432",
    }})
    def test_backup_postgres_scheduled_dumps_compresses_and_uploads(self):
        backup_dir = Path(self.temp_dir.name)

        def fake_pg_dump(cmd, **kwargs):
            dump_path = Path(cmd[cmd.index("--file") + 1])
            dump_path.write_text("-- pg dump content")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with override_settings(BASE_DIR=backup_dir):
            with patch("bmx.cron.subprocess.run", side_effect=fake_pg_dump) as run_mock, \
                    patch("bmx.cron._upload_backup_offsite") as upload_mock:
                bmx_cron.backup_postgres_scheduled()

        cmd = run_mock.call_args.args[0]
        self.assertEqual(cmd[0], "pg_dump")
        self.assertIn("bmx_prod", cmd)
        for flag, value in (("--username", "bmx"), ("--host", "localhost"), ("--port", "5432")):
            self.assertIn(flag, cmd)
            self.assertEqual(cmd[cmd.index(flag) + 1], value)

        env = run_mock.call_args.kwargs["env"]
        self.assertEqual(env["PGPASSWORD"], "secret")

        backups = list(backup_dir.glob("db-bmx_prod.bak-*.gz"))
        self.assertEqual(len(backups), 1)
        upload_mock.assert_called_once_with(backups[0])

    @override_settings(DATABASES={"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "bmx_prod",
    }})
    def test_backup_postgres_scheduled_handles_missing_pg_dump_gracefully(self):
        with patch("bmx.cron.subprocess.run", side_effect=FileNotFoundError):
            bmx_cron.backup_postgres_scheduled()
