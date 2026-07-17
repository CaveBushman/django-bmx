from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from PIL import Image

from accounts.models import AccountRiderLink, AvatarChangeRequest
from bmx.form_protection import build_flow_token
from club.models import Club
from event.models import CreditTransaction, Event, RaceRun, Result, SeasonSettings
from rider.models import (
    Rider,
    RiderStatsCharge,
    RiderStatsSubscription,
    TrainerClubCharge,
    TrainerClubSubscription,
)
from rider.admin import RiderAdmin
from rider.rider import get_rider_data
from rider.subscriptions import (
    cancel_trainer_club_subscription,
    get_active_trainer_extended_subscription,
    has_active_trainer_club_extended_access,
    has_active_trainer_club_stats_access,
    purchase_trainer_club_subscription,
)


User = get_user_model()


class RiderAdminSearchTests(TestCase):
    def test_rider_admin_search_ignores_case_and_diacritics(self):
        club = Club.objects.create(team_name="Search Club")
        rider = Rider.objects.create(
            uci_id=12345679999,
            first_name="Šimon",
            last_name="Černý",
            gender="Muž",
            date_of_birth=date(2012, 1, 1),
            club=club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
        )

        request = RequestFactory().get("/admin/rider/rider/")
        request.user = User.objects.create_user(
            first_name="Admin",
            last_name="User",
            username="rider_search_admin",
            email="rider_search_admin@example.com",
            password="StrongPass123!",
        )
        admin_instance = RiderAdmin(Rider, admin.site)

        queryset, _ = admin_instance.get_search_results(
            request,
            Rider.objects.all(),
            "CERNY",
        )

        self.assertIn(rider, list(queryset))


class RiderRequestProtectionTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(team_name="Request Club", is_active=True)

    def rider_request_payload(self, **overrides):
        payload = {
            "lookup_confirmed": "1",
            "uci_id": "12345678901",
            "first_name": "Test",
            "last_name": "Rider",
            "date_of_birth": "2012-01-01",
            "gender": "Muž",
            "plate": "12",
            "club": str(self.club.id),
            "is20": "on",
            "emergency-contact": "Parent",
            "emergency-phone": "777123123",
            "form_token": build_flow_token("rider_request", timezone.now() - timedelta(seconds=5)),
            "website": "",
        }
        payload.update(overrides)
        return payload

    def test_rider_request_page_contains_form_protection_token(self):
        response = self.client.get(reverse("rider:new"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="form_token"', html=False)

    def test_rider_request_rejects_honeypot_submission(self):
        response = self.client.post(
            reverse("rider:new"),
            self.rider_request_payload(website="bot"),
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Rider.objects.filter(uci_id="12345678901").exists())

    @patch("rider.views.account.get_rider_data", return_value=(None, "Nastala chyba: 500"))
    def test_rider_request_rejects_valid_licence_when_detail_endpoint_fails(
        self, _get_rider_data
    ):
        response = self.client.post(
            reverse("rider:new"),
            self.rider_request_payload(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Rider.objects.filter(uci_id="12345678901").exists())
        self.assertContains(response, "Údaje licence se nepodařilo načíst z ČSC")

    @patch("rider.views.account.get_rider_data")
    def test_rider_request_uses_complete_identity_returned_by_licence(self, get_rider_data):
        get_rider_data.return_value = (
            {
                "firstName": "Jan",
                "lastName": "NOVÁK",
                "birth": "2011-05-06T00:00:00",
                "sex": {"code": "M"},
            },
            None,
        )

        response = self.client.post(
            reverse("rider:new"),
            self.rider_request_payload(first_name="Podvržené", last_name="Jméno"),
        )

        self.assertEqual(response.status_code, 200)
        rider = Rider.objects.get(uci_id="12345678901")
        self.assertEqual(rider.first_name, "Jan")
        self.assertEqual(rider.last_name, "Novák")
        self.assertEqual(str(rider.date_of_birth), "2011-05-06")
        self.assertEqual(rider.gender, "Muž")


class RiderLicenceLookupTests(TestCase):
    @patch("rider.views.directory.get_rider_data", return_value=(None, "Nastala chyba: 500"))
    def test_lookup_rejects_when_personal_details_endpoint_fails(self, _get_rider_data):
        response = self.client.get(
            reverse("rider:new-licence-lookup"),
            {"uci_id": "10046761357"},
        )

        self.assertEqual(response.status_code, 502)
        payload = response.json()
        self.assertFalse(payload["ok"])

    @patch("rider.views.directory.get_rider_data")
    def test_lookup_returns_all_required_personal_details(self, get_rider_data):
        get_rider_data.return_value = (
            {
                "firstName": "Jana",
                "lastName": "NOVÁKOVÁ",
                "birth": "2012-04-03T00:00:00",
                "sex": {"code": "F"},
            },
            None,
        )

        response = self.client.get(
            reverse("rider:new-licence-lookup"),
            {"uci_id": "10046761357"},
        )

        self.assertEqual(response.status_code, 200)
        rider = response.json()["rider"]
        self.assertEqual(rider["first_name"], "Jana")
        self.assertEqual(rider["last_name"], "Nováková")
        self.assertEqual(rider["date_of_birth"], "2012-04-03")
        self.assertEqual(rider["gender"], "Žena")

    @patch("rider.views.directory.get_rider_data", return_value=(None, "ČSC chyba záznamu (500)"))
    def test_lookup_reports_record_error_directs_to_admin(self, _get_rider_data):
        response = self.client.get(
            reverse("rider:new-licence-lookup"),
            {"uci_id": "10046761357"},
        )

        self.assertEqual(response.status_code, 502)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertIn("administraci", payload["message"])

    @patch("rider.views.directory.get_rider_data", return_value=(None, "Licence nebyla nalezena"))
    def test_lookup_rejects_invalid_uci_id(self, _get_rider_data):
        response = self.client.get(
            reverse("rider:new-licence-lookup"),
            {"uci_id": "10046761357"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()["ok"])


class CzechCyclingLicenceInfoApiTests(TestCase):
    @patch("rider.rider.requests.get")
    @patch("rider.rider.get_api_token", return_value="token")
    def test_personal_details_lookup_uses_licenseinfo_without_year(
        self, _get_token, request_get
    ):
        api_response = Mock(status_code=200, ok=True)
        api_response.text = ""
        api_response.json.return_value = {
            "firstName": "Jan",
            "lastName": "Novák",
            "birth": "2010-01-02T00:00:00",
            "sex": {"code": "M"},
        }
        request_get.return_value = api_response

        data, error = get_rider_data("10046761357")

        self.assertIsNone(error)
        self.assertEqual(data["firstName"], "Jan")
        request_url = request_get.call_args.args[0]
        self.assertEqual(
            request_url,
            "https://portal.api.czechcyclingfederation.com/api/services/licenseinfo?uciId=10046761357",
        )
        self.assertNotIn("year", request_url.lower())

    @patch("rider.rider.requests.get")
    @patch("rider.rider.get_api_token", return_value="token")
    def test_server_error_reported_as_record_error(self, _get_token, request_get):
        # ČSC licenseinfo umí pro konkrétní (rozbitý) záznam vracet trvalé 500,
        # i když validuciid hlásí platnou licenci – musí být odlišené od 404.
        api_response = Mock(status_code=500, ok=False)
        api_response.text = '{"error":{"message":"An internal error occurred"}}'
        request_get.return_value = api_response

        data, error = get_rider_data("10046761357")

        self.assertIsNone(data)
        self.assertIn("chyba záznamu", error)
        self.assertNotIn("nebyla nalezena", error)


class RiderListTemplateSafetyTests(TestCase):
    def test_rider_list_uses_external_script_and_no_inline_handlers(self):
        club = Club.objects.create(team_name="Template Club")
        Rider.objects.create(
            uci_id=12345678888,
            first_name="Template",
            last_name="Rider",
            gender="Muž",
            date_of_birth=date(2012, 1, 1),
            club=club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
        )

        response = self.client.get(reverse("rider:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "js/riders_list.js")
        self.assertNotContains(response, "onclick=")
        self.assertNotContains(response, "onerror=")
        self.assertContains(response, "data-rider-detail-url")
        self.assertContains(response, "data-rider-photo")

    def test_plate_search_uses_external_script_and_no_inline_handlers(self):
        response = self.client.get(reverse("rider:plate-search"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "js/rider_search_forms.js")
        self.assertNotContains(response, "onsubmit=")
        self.assertNotContains(response, "oninput=")
        self.assertContains(response, "data-plate-search-form")
        self.assertContains(response, "data-plate-search-input")

    def test_transponder_search_uses_external_script_and_no_inline_handlers(self):
        response = self.client.get(reverse("rider:transponder-search"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "js/rider_search_forms.js")
        self.assertNotContains(response, "onsubmit=")
        self.assertNotContains(response, "oninput=")
        self.assertContains(response, "data-transponder-search-form")
        self.assertContains(response, "data-transponder-search-input")

    def test_premium_templates_use_external_ui_script_and_no_inline_handlers(self):
        compare_template = (
            Path(settings.BASE_DIR) / "rider" / "templates" / "rider" / "rider-compare.html"
        ).read_text(encoding="utf-8")
        premium_template = (
            Path(settings.BASE_DIR) / "rider" / "templates" / "rider" / "rider-premium-stats.html"
        ).read_text(encoding="utf-8")

        self.assertIn("js/rider_premium_ui.js", compare_template)
        self.assertIn("js/rider_premium_ui.js", premium_template)
        self.assertNotIn("onchange=", compare_template)
        self.assertNotIn("<script>", compare_template)
        self.assertNotIn("onchange=", premium_template)
        self.assertNotIn("<script>", premium_template)
        self.assertIn("data-auto-submit", compare_template)
        self.assertIn("data-auto-submit", premium_template)

    def test_rider_request_template_uses_external_script_and_no_inline_submit(self):
        request_template = (
            Path(settings.BASE_DIR) / "rider" / "templates" / "rider" / "rider-request.html"
        ).read_text(encoding="utf-8")

        self.assertIn("js/rider_request.js", request_template)
        self.assertNotIn('onsubmit="', request_template)
        self.assertNotIn("<script>", request_template)
        self.assertIn('id="rider-request-form"', request_template)
        self.assertIn("data-lookup-url=", request_template)


class AccountSettingsLinkedRidersTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            first_name="David",
            last_name="Parent",
            username="linked_parent",
            email="linked_parent@example.com",
            password="StrongPass123!",
        )
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])
        self.club = Club.objects.create(team_name="Linked Riders Club")
        self.rider = Rider.objects.create(
            uci_id=12345670077,
            first_name="Adam",
            last_name="Rider",
            gender="Muž",
            date_of_birth=date(2012, 4, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
        )
        AccountRiderLink.objects.create(account=self.user, rider=self.rider)

    def test_account_page_shows_linked_rider(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("user:account"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profily jezdců navázané na účet")
        self.assertContains(response, "Adam Rider")
        self.assertContains(response, "Linked Riders Club")

    def _build_test_image(self, *, name="avatar.png", color=(20, 100, 220)):
        buffer = BytesIO()
        image = Image.new("RGB", (240, 240), color=color)
        image.save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def test_account_can_submit_own_avatar_change_request(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("user:account"),
            {
                "action": "submit-avatar-request",
                "target_type": "account",
                "target_id": str(self.user.pk),
                "avatar_image": self._build_test_image(),
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        avatar_request = AvatarChangeRequest.objects.get(target_account=self.user)
        self.assertEqual(avatar_request.status, AvatarChangeRequest.STATUS_PENDING)
        self.assertContains(response, "odeslán ke schválení")

    def test_account_can_submit_linked_rider_avatar_change_request(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("user:account"),
            {
                "action": "submit-avatar-request",
                "target_type": "rider",
                "target_id": str(self.rider.pk),
                "avatar_image": self._build_test_image(name="rider-avatar.png"),
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        avatar_request = AvatarChangeRequest.objects.get(target_rider=self.rider)
        self.assertEqual(avatar_request.status, AvatarChangeRequest.STATUS_PENDING)
        self.assertContains(response, "odeslán ke schválení")

    def test_account_cannot_submit_avatar_for_unlinked_rider(self):
        other_rider = Rider.objects.create(
            uci_id=12345670078,
            first_name="Petr",
            last_name="Other",
            gender="Muž",
            date_of_birth=date(2013, 4, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("user:account"),
            {
                "action": "submit-avatar-request",
                "target_type": "rider",
                "target_id": str(other_rider.pk),
                "avatar_image": self._build_test_image(name="other.png"),
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AvatarChangeRequest.objects.filter(target_rider=other_rider).exists())
        self.assertContains(response, "Nemůžeš žádat změnu avataru pro cizího jezdce")


class RiderAdminAvatarModerationTests(TestCase):
    def _build_test_image(self, *, name="avatar.png", color=(30, 120, 220)):
        buffer = BytesIO()
        image = Image.new("RGB", (240, 240), color=color)
        image.save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def setUp(self):
        self.staff_user = User.objects.create_user(
            first_name="Staff",
            last_name="Moderator",
            username="staff_moderator",
            email="staff_moderator@example.com",
            password="StrongPass123!",
        )
        self.staff_user.is_active = True
        self.staff_user.is_staff = True
        self.staff_user.save(update_fields=["is_active", "is_staff"])

        AvatarChangeRequest.objects.create(
            uploaded_by=self.staff_user,
            target_account=self.staff_user,
            image=self._build_test_image(),
        )

    def test_rider_admin_shows_avatar_moderation_link_and_badge(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("rider:admin"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pending_avatar_count"], 1)
        self.assertContains(response, "Schvalování avatarů")
        self.assertContains(response, reverse("accounts:avatar-moderation"))
        self.assertContains(response, "Ruční kontrola nových avatarů")

    def test_staff_user_sees_avatar_badge_in_navbar(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("user:account"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AVATAR")
        self.assertContains(response, reverse("accounts:avatar-moderation"))


class RiderAdminSearchTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            first_name="Admin",
            last_name="Rider",
            username="rider_admin",
            email="rider_admin@example.com",
            password="StrongPass123!",
        )
        self.staff_user.is_active = True
        self.staff_user.is_staff = True
        self.staff_user.is_superuser = True
        self.staff_user.save(update_fields=["is_active", "is_staff", "is_superuser"])

        self.club = Club.objects.create(team_name="Admin Search Club")
        self.admin_instance = RiderAdmin(Rider, admin.site)

    def test_changelist_renders_for_text_search_when_rider_has_no_photo(self):
        Rider.objects.create(
            uci_id=12345670090,
            first_name="Ivan",
            last_name="Zelenko",
            gender="Muž",
            date_of_birth=date(2012, 4, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            photo="",
        )

        request = RequestFactory().get("/bmx-admin/rider/rider/", {"q": "Zelenko"})
        request.user = self.staff_user

        response = self.admin_instance.changelist_view(request)
        response.render()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Zelenko")

    def test_changelist_keeps_numeric_search_for_legacy_plate_field(self):
        Rider.objects.create(
            uci_id=12345670091,
            first_name="Numeric",
            last_name="Plate",
            gender="Muž",
            date_of_birth=date(2012, 5, 1),
            club=self.club,
            plate=321,
            plate_text="",
            is_active=True,
            is_approved=True,
            valid_licence=True,
            photo="",
        )

        request = RequestFactory().get("/bmx-admin/rider/rider/", {"q": "321"})
        request.user = self.staff_user

        response = self.admin_instance.changelist_view(request)
        response.render()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Plate")

    def test_thumbnail_falls_back_to_initials_when_photo_is_missing(self):
        rider = Rider.objects.create(
            uci_id=12345670093,
            first_name="Adam",
            last_name="Benes",
            gender="Muž",
            date_of_birth=date(2012, 5, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            photo="",
        )

        thumbnail = self.admin_instance.thumbnail(rider)

        self.assertIn("AB", str(thumbnail))
        self.assertNotIn("<img", str(thumbnail))

    def test_rider_admin_data_quality_summary_shows_detected_issues(self):
        rider = Rider.objects.create(
            uci_id=12345670092,
            first_name="Issue",
            last_name="Finder",
            gender="Muž",
            date_of_birth=date(2012, 5, 1),
            club=None,
            is_active=True,
            is_approved=False,
            valid_licence=True,
            is_20=True,
            points_24=20,
            photo="images/riders/uni.jpeg",
        )

        summary = self.admin_instance.data_quality_summary(rider)

        self.assertIn("Chybí klub", str(summary))
        self.assertIn("Chybí fotka", str(summary))
        self.assertIn('Chybí čip 20"', str(summary))
        self.assertIn('Body 24" bez aktivní disciplíny', str(summary))

    def test_rider_admin_change_view_renders_for_profile_without_data_issues(self):
        rider = Rider.objects.create(
            uci_id=12345670094,
            first_name="Detail",
            last_name="Rider",
            gender="Muž",
            date_of_birth=date(2012, 5, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            photo="images/riders/detail.jpg",
        )
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("admin:rider_rider_change", args=[rider.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Detail Rider")


class RiderPremiumSubscriptionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            first_name="Premium",
            last_name="User",
            username="premium_user",
            email="premium@example.com",
            password="StrongPass123!",
        )
        self.user.is_active = True
        self.user.save()

        self.club = Club.objects.create(team_name="Premium Club")
        self.season = SeasonSettings.objects.create(
            year=timezone.now().year,
            rider_stats_monthly_price=50,
        )
        self.rider = Rider.objects.create(
            uci_id=12345670001,
            first_name="Fast",
            last_name="Rider",
            gender="Muž",
            date_of_birth=date(2010, 5, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
        )
        self.event = Event.objects.create(
            name="Premium Race",
            date=date.today() - timedelta(days=7),
            organizer=self.club,
            reg_open=False,
            type_for_ranking="Volný závod",
        )
        self.result = Result.objects.create(
            event=self.event,
            rider=self.rider,
            date=self.event.date,
            event_type=self.event.type_for_ranking,
            organizer=self.club.team_name,
            category=self.rider.class_20,
            place=1,
            points=100,
        )
        self.run = RaceRun.objects.create(
            result=self.result,
            event=self.event,
            rider=self.rider,
            is_20=True,
            is_beginner=False,
            round_type="MOTO",
            round_number=1,
            lane=3,
            finish_time=34.12,
            hill_time=2.56,
            split_1=8.91,
        )

    def test_subscribe_creates_subscription_and_deducts_credit(self):
        CreditTransaction.objects.create(
            user=self.user,
            amount=100,
            transaction_id="credit-1",
            payment_complete=True,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("rider:premium-stats-subscribe", kwargs={"pk": self.rider.uci_id})
        )

        self.assertRedirects(response, reverse("rider:premium-stats", kwargs={"pk": self.rider.uci_id}))
        subscription = RiderStatsSubscription.objects.get(user=self.user, rider=self.rider)
        charge = RiderStatsCharge.objects.get(user=self.user, rider=self.rider)

        self.user.refresh_from_db()
        self.assertEqual(subscription.status, RiderStatsSubscription.STATUS_ACTIVE)
        self.assertTrue(subscription.auto_renew)
        self.assertEqual(subscription.monthly_price, 50)
        self.assertEqual(charge.amount, 50)
        self.assertEqual(self.user.credit, 50)

    def test_premium_stats_requires_subscription(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("rider:premium-stats", kwargs={"pk": self.rider.uci_id}),
            follow=True,
        )

        self.assertRedirects(response, reverse("rider:detail", kwargs={"pk": self.rider.uci_id}))
        self.assertContains(response, "aktivní předplatné")

    def test_premium_stats_page_renders_track_times_for_active_subscription(self):
        CreditTransaction.objects.create(
            user=self.user,
            amount=100,
            transaction_id="credit-2",
            payment_complete=True,
        )
        self.client.force_login(self.user)
        self.client.post(reverse("rider:premium-stats-subscribe", kwargs={"pk": self.rider.uci_id}))

        response = self.client.get(reverse("rider:premium-stats", kwargs={"pk": self.rider.uci_id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "34,12")
        self.assertContains(response, "2,56")
        self.assertContains(response, "8,91")

    def test_staff_can_access_premium_stats_without_subscription(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.client.force_login(self.user)

        response = self.client.get(reverse("rider:premium-stats", kwargs={"pk": self.rider.uci_id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Administrátorský přístup")

    def test_premium_stats_supports_track_selection(self):
        CreditTransaction.objects.create(
            user=self.user,
            amount=100,
            transaction_id="credit-3",
            payment_complete=True,
        )
        other_club = Club.objects.create(team_name="Secondary Track")
        other_event = Event.objects.create(
            name="Secondary Race",
            date=date.today() - timedelta(days=3),
            organizer=other_club,
            reg_open=False,
            type_for_ranking="Volný závod",
        )
        other_result = Result.objects.create(
            event=other_event,
            rider=self.rider,
            date=other_event.date,
            event_type=other_event.type_for_ranking,
            organizer=other_club.team_name,
            category=self.rider.class_20,
            place=4,
            points=50,
        )
        RaceRun.objects.create(
            result=other_result,
            event=other_event,
            rider=self.rider,
            is_20=True,
            is_beginner=False,
            round_type="FINAL",
            lane=5,
            place="4th",
            finish_time=35.44,
        )

        self.client.force_login(self.user)
        self.client.post(reverse("rider:premium-stats-subscribe", kwargs={"pk": self.rider.uci_id}))

        response = self.client.get(
            reverse("rider:premium-stats", kwargs={"pk": self.rider.uci_id}),
            {"track": other_club.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Secondary Track")
        self.assertContains(response, "Traťový profil")
        self.assertContains(response, "35,44")

    def test_premium_stats_auto_selects_track_with_most_timed_runs(self):
        CreditTransaction.objects.create(
            user=self.user,
            amount=100,
            transaction_id="credit-3b",
            payment_complete=True,
        )
        other_club = Club.objects.create(team_name="Secondary Track")
        older_event = Event.objects.create(
            name="Secondary Race One",
            date=date.today() - timedelta(days=4),
            organizer=other_club,
            reg_open=False,
            type_for_ranking="Volný závod",
        )
        newer_event = Event.objects.create(
            name="Secondary Race Two",
            date=date.today() - timedelta(days=3),
            organizer=other_club,
            reg_open=False,
            type_for_ranking="Volný závod",
        )
        older_result = Result.objects.create(
            event=older_event,
            rider=self.rider,
            date=older_event.date,
            event_type=older_event.type_for_ranking,
            organizer=other_club.team_name,
            category=self.rider.class_20,
            place=4,
            points=50,
        )
        newer_result = Result.objects.create(
            event=newer_event,
            rider=self.rider,
            date=newer_event.date,
            event_type=newer_event.type_for_ranking,
            organizer=other_club.team_name,
            category=self.rider.class_20,
            place=2,
            points=75,
        )
        RaceRun.objects.create(
            result=older_result,
            event=older_event,
            rider=self.rider,
            is_20=True,
            is_beginner=False,
            round_type="MOTO",
            round_number=1,
            lane=5,
            place="4th",
            finish_time=35.44,
        )
        RaceRun.objects.create(
            result=newer_result,
            event=newer_event,
            rider=self.rider,
            is_20=True,
            is_beginner=False,
            round_type="FINAL",
            lane=6,
            place="2nd",
            finish_time=35.01,
        )

        self.client.force_login(self.user)
        self.client.post(reverse("rider:premium-stats-subscribe", kwargs={"pk": self.rider.uci_id}))

        response = self.client.get(reverse("rider:premium-stats", kwargs={"pk": self.rider.uci_id}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_track"]["id"], other_club.id)
        self.assertContains(response, "Secondary Track")
        self.assertContains(response, "35,44")
        self.assertContains(response, "35,01")

    def test_premium_compare_page_renders_hill_and_head_to_head(self):
        CreditTransaction.objects.create(
            user=self.user,
            amount=100,
            transaction_id="credit-4",
            payment_complete=True,
        )
        opponent = Rider.objects.create(
            uci_id=12345670002,
            first_name="Marek",
            last_name="Souper",
            gender="Muž",
            date_of_birth=date(2010, 5, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            class_20=self.rider.class_20,
            is_20=True,
        )
        opponent_result = Result.objects.create(
            event=self.event,
            rider=opponent,
            date=self.event.date,
            event_type=self.event.type_for_ranking,
            organizer=self.club.team_name,
            category=opponent.class_20,
            place=2,
            points=80,
            is_20=True,
        )
        RaceRun.objects.create(
            result=opponent_result,
            event=self.event,
            rider=opponent,
            category=opponent.class_20,
            is_beginner=False,
            is_20=True,
            round_type="MOTO",
            round_number=1,
            heat_code="1",
            lane=4,
            place="2nd",
            finish_time=34.55,
            hill_time=2.61,
        )
        self.client.force_login(self.user)
        self.client.post(reverse("rider:premium-stats-subscribe", kwargs={"pk": self.rider.uci_id}))

        response = self.client.get(
            reverse("rider:premium-compare", kwargs={"pk": self.rider.uci_id}),
            {
                "track": self.club.id,
                "wheel": "20",
                "years": "3",
                "opponent": opponent.uci_id,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Median hill")
        self.assertContains(response, "Porovnání jezdců")
        self.assertContains(response, "Motos")
        self.assertContains(response, "1 : 0")

    def test_premium_compare_page_populates_wheels_and_candidates_for_selected_track(self):
        CreditTransaction.objects.create(
            user=self.user,
            amount=100,
            transaction_id="credit-5",
            payment_complete=True,
        )
        opponent = Rider.objects.create(
            uci_id=12345670003,
            first_name="Petr",
            last_name="Souper",
            gender="Muž",
            date_of_birth=date(2010, 5, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            class_20=self.rider.class_20,
            is_20=True,
        )
        opponent_result = Result.objects.create(
            event=self.event,
            rider=opponent,
            date=self.event.date,
            event_type=self.event.type_for_ranking,
            organizer=self.club.team_name,
            category=opponent.class_20,
            place=2,
            points=80,
            is_20=True,
        )
        RaceRun.objects.create(
            result=opponent_result,
            event=self.event,
            rider=opponent,
            category=opponent.class_20,
            is_beginner=False,
            is_20=True,
            round_type="MOTO",
            round_number=1,
            heat_code="1",
            lane=4,
            place="2nd",
            finish_time=34.55,
        )

        self.client.force_login(self.user)
        self.client.post(reverse("rider:premium-stats-subscribe", kwargs={"pk": self.rider.uci_id}))

        track_response = self.client.get(
            reverse("rider:premium-compare", kwargs={"pk": self.rider.uci_id}),
            {"track": self.club.id, "years": "2"},
        )
        self.assertEqual(track_response.status_code, 200)
        self.assertContains(track_response, 'value="20"')

        wheel_response = self.client.get(
            reverse("rider:premium-compare", kwargs={"pk": self.rider.uci_id}),
            {"track": self.club.id, "wheel": "20", "years": "2"},
        )
        self.assertEqual(wheel_response.status_code, 200)
        self.assertContains(wheel_response, "Petr Souper")

    def test_premium_stats_pdf_export_requires_trainer_extended(self):
        CreditTransaction.objects.create(
            user=self.user,
            amount=100,
            transaction_id="credit-6",
            payment_complete=True,
        )
        self.client.force_login(self.user)
        self.client.post(reverse("rider:premium-stats-subscribe", kwargs={"pk": self.rider.uci_id}))

        page_response = self.client.get(
            reverse("rider:premium-stats", kwargs={"pk": self.rider.uci_id}),
            {"track": self.club.id, "wheel": "20", "years": "2"},
        )
        self.assertEqual(page_response.status_code, 200)
        self.assertNotContains(page_response, reverse("rider:premium-stats-pdf", kwargs={"pk": self.rider.uci_id}))

        export_response = self.client.get(
            reverse("rider:premium-stats-pdf", kwargs={"pk": self.rider.uci_id}),
            {"track": self.club.id, "wheel": "20", "years": "2"},
            follow=True,
        )
        self.assertRedirects(export_response, reverse("rider:premium-stats", kwargs={"pk": self.rider.uci_id}))
        self.assertContains(export_response, "trainer extended")


class RiderDetailTemplateTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(team_name="Detail Club")
        self.rider = Rider.objects.create(
            uci_id=12345670111,
            first_name="Mobile",
            last_name="Card",
            gender="Muž",
            date_of_birth=date(2010, 5, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            is_20=True,
            class_20="Boys 15/16",
        )
        self.event = Event.objects.create(
            name="Spring Race",
            date=date.today() - timedelta(days=14),
            organizer=self.club,
            reg_open=False,
            type_for_ranking="Volný závod",
        )
        Result.objects.create(
            event=self.event,
            rider=self.rider,
            date=self.event.date,
            event_type=self.event.type_for_ranking,
            organizer=self.club.team_name,
            category="Boys 15/16",
            place=2,
            points=45,
            marked_20=True,
        )
        Result.objects.create(
            event=self.event,
            rider=self.rider,
            date=self.event.date - timedelta(days=7),
            event_type="Cruiser",
            organizer=self.club.team_name,
            category="Cruiser 15/16",
            place=3,
            points=18,
            marked_24=True,
        )
        Result.objects.create(
            event=self.event,
            rider=self.rider,
            date=self.event.date - timedelta(days=21),
            event_type="Volný závod",
            organizer=self.club.team_name,
            category="Boys 15/16",
            place=5,
            points=0,
            marked_20=False,
            marked_24=False,
        )

    def test_rider_detail_renders_card_layout_for_last_year_results(self):
        response = self.client.get(reverse("rider:detail", kwargs={"pk": self.rider.uci_id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rider-results-grid")
        self.assertContains(response, "Spring Race")
        self.assertContains(response, "45 b.")
        self.assertContains(response, "Umístění:")
        self.assertContains(response, 'Body do 20"')
        self.assertContains(response, 'Body do 24"')
        self.assertContains(response, "Mimo ranking")
        self.assertContains(response, ">45<", html=False)
        self.assertContains(response, ">18<", html=False)
        self.assertContains(response, ">1<", html=False)


class TrainerClubSubscriptionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            first_name="Coach",
            last_name="User",
            username="coach_user",
            email="coach@example.com",
            password="StrongPass123!",
        )
        self.user.is_active = True
        self.user.is_trainer = True
        self.club = Club.objects.create(team_name="Coach Club")
        self.other_club = Club.objects.create(team_name="Second Club")
        self.user.save()
        self.user.trainer_clubs.add(self.club, self.other_club)

        self.season = SeasonSettings.objects.create(
            year=timezone.now().year,
            rider_stats_monthly_price=50,
            trainer_club_stats_monthly_price=300,
            trainer_extended_monthly_price=600,
        )
        CreditTransaction.objects.create(
            user=self.user,
            amount=2000,
            transaction_id="coach-credit",
            payment_complete=True,
        )
        self.rider = Rider.objects.create(
            uci_id=12345678888,
            first_name="Trainer",
            last_name="Rider",
            gender="Muž",
            date_of_birth=date(2010, 5, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            is_20=True,
        )
        self.event = Event.objects.create(
            name="Trainer Race",
            date=date.today() - timedelta(days=10),
            organizer=self.club,
            reg_open=False,
            type_for_ranking="Volný závod",
        )
        self.result = Result.objects.create(
            event=self.event,
            rider=self.rider,
            date=self.event.date,
            event_type=self.event.type_for_ranking,
            organizer=self.club.team_name,
            category=self.rider.class_20,
            place=2,
            points=80,
            is_20=True,
        )
        self.run = RaceRun.objects.create(
            result=self.result,
            event=self.event,
            rider=self.rider,
            is_20=True,
            is_beginner=False,
            round_type="MOTO",
            round_number=1,
            lane=4,
            finish_time=34.78,
            hill_time=2.63,
            split_1=8.94,
        )

    def test_purchase_trainer_club_stats_subscription_is_billed_per_club(self):
        subscription, created = purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )

        self.assertTrue(created)
        self.user.refresh_from_db()
        self.assertEqual(subscription.club, self.club)
        self.assertEqual(subscription.product, TrainerClubSubscription.PRODUCT_CLUB_STATS)
        self.assertEqual(subscription.monthly_price, 300)
        self.assertTrue(
            TrainerClubCharge.objects.filter(
                user=self.user,
                club=self.club,
                product=TrainerClubSubscription.PRODUCT_CLUB_STATS,
                amount=300,
            ).exists()
        )
        self.assertTrue(has_active_trainer_club_stats_access(self.user, self.club))
        self.assertFalse(has_active_trainer_club_extended_access(self.user, self.club))

    def test_purchase_extended_trainer_subscription_is_global_for_all_stats_clubs(self):
        purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )
        purchase_trainer_club_subscription(
            self.user,
            self.other_club,
            TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )
        subscription, created = purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_EXTENDED,
        )

        self.assertTrue(created)
        self.user.refresh_from_db()
        self.assertEqual(subscription.product, TrainerClubSubscription.PRODUCT_EXTENDED)
        self.assertEqual(subscription.monthly_price, 600)
        self.assertEqual(
            TrainerClubSubscription.objects.filter(
                user=self.user,
                product=TrainerClubSubscription.PRODUCT_EXTENDED,
            ).count(),
            1,
        )
        self.assertIsNotNone(get_active_trainer_extended_subscription(self.user))
        self.assertTrue(has_active_trainer_club_stats_access(self.user, self.club))
        self.assertTrue(has_active_trainer_club_extended_access(self.user, self.club))
        self.assertTrue(has_active_trainer_club_extended_access(self.user, self.other_club))


    def test_extended_requires_active_stats_on_club(self):
        purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )
        purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_EXTENDED,
        )

        self.assertTrue(has_active_trainer_club_extended_access(self.user, self.club))
        self.assertFalse(has_active_trainer_club_extended_access(self.user, self.other_club))

    def test_trainer_stats_subscriptions_remain_separate_for_each_club(self):
        purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )
        purchase_trainer_club_subscription(
            self.user,
            self.other_club,
            TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )

        self.assertEqual(
            TrainerClubSubscription.objects.filter(
                user=self.user,
                product=TrainerClubSubscription.PRODUCT_CLUB_STATS,
            ).count(),
            2,
        )

    def test_extended_cannot_be_purchased_without_any_stats_subscription(self):
        with self.assertRaisesMessage(ValueError, "alespoň jednoho klubu"):
            purchase_trainer_club_subscription(
                self.user,
                self.club,
                TrainerClubSubscription.PRODUCT_EXTENDED,
            )

    def test_disabling_last_stats_auto_renew_disables_extended_auto_renew(self):
        stats_subscription, _ = purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )
        extended_subscription, _ = purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_EXTENDED,
        )

        self.assertTrue(extended_subscription.auto_renew)
        cancel_trainer_club_subscription(stats_subscription)
        extended_subscription.refresh_from_db()

        self.assertFalse(extended_subscription.auto_renew)

    def test_extended_expires_when_no_active_stats_remain(self):
        stats_subscription, _ = purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )
        extended_subscription, _ = purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_EXTENDED,
        )

        stats_subscription.expires_at = timezone.now() - timedelta(minutes=1)
        stats_subscription.save(update_fields=["expires_at", "updated"])

        active_extended = get_active_trainer_extended_subscription(self.user)
        extended_subscription.refresh_from_db()

        self.assertIsNone(active_extended)
        self.assertEqual(extended_subscription.status, TrainerClubSubscription.STATUS_EXPIRED)
        self.assertFalse(extended_subscription.auto_renew)

    def test_trainer_riders_csv_export_includes_utf8_bom_for_excel(self):
        purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )
        purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_EXTENDED,
        )
        Rider.objects.create(
            uci_id=12345679999,
            first_name="Žaneta",
            last_name="Černá",
            gender="Žena",
            date_of_birth=date(2010, 5, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            email="zaneta@example.com",
        )

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("user:trainer-club-riders-export", kwargs={"club_id": self.club.id, "export_format": "csv"})
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith("\ufeff".encode("utf-8")))
        self.assertIn("Žaneta".encode("utf-8"), response.content)

    def test_trainer_extended_can_export_rider_premium_stats_pdf(self):
        purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )
        purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_EXTENDED,
        )

        self.client.force_login(self.user)
        page_response = self.client.get(
            reverse("rider:premium-stats", kwargs={"pk": self.rider.uci_id}),
            {"track": self.club.id, "wheel": "20", "years": "2"},
        )
        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, reverse("rider:premium-stats-pdf", kwargs={"pk": self.rider.uci_id}))

        export_response = self.client.get(
            reverse("rider:premium-stats-pdf", kwargs={"pk": self.rider.uci_id}),
            {"track": self.club.id, "wheel": "20", "years": "2"},
        )
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(export_response["Content-Type"], "application/pdf")
        self.assertTrue(export_response.content.startswith(b"%PDF"))

    def test_trainer_kpi_xlsx_export_has_formatted_header_and_freeze_panes(self):
        purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )
        purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_EXTENDED,
        )
        rider = Rider.objects.create(
            uci_id=12345678889,
            first_name="KPI",
            last_name="Rider",
            gender="Muž",
            date_of_birth=date(2010, 5, 1),
            club=self.club,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            is_20=True,
        )
        event = Event.objects.create(
            name="Coach KPI Race",
            date=date.today() - timedelta(days=7),
            organizer=self.club,
            reg_open=False,
            type_for_ranking="Volný závod",
        )
        result = Result.objects.create(
            event=event,
            rider=rider,
            date=event.date,
            event_type=event.type_for_ranking,
            organizer=self.club.team_name,
            category=rider.class_20,
            place=3,
            points=70,
            is_20=True,
        )
        RaceRun.objects.create(
            result=result,
            event=event,
            rider=rider,
            is_20=True,
            is_beginner=False,
            round_type="FINAL",
            finish_time=33.21,
            hill_time=2.45,
            split_1=10.11,
        )

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("user:trainer-club-kpi-export", kwargs={"club_id": self.club.id, "export_format": "xlsx"})
        )

        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content))
        worksheet = workbook["KPI"]
        self.assertEqual(worksheet.freeze_panes, "A2")
        self.assertEqual(worksheet["A1"].value, "UCI ID")
        self.assertTrue(worksheet["A1"].font.bold)
        self.assertEqual(worksheet["A2"].value, rider.uci_id)

    def test_trainer_export_rejects_unsupported_format(self):
        purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_CLUB_STATS,
        )
        purchase_trainer_club_subscription(
            self.user,
            self.club,
            TrainerClubSubscription.PRODUCT_EXTENDED,
        )

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("user:trainer-club-riders-export", kwargs={"club_id": self.club.id, "export_format": "pdf"})
        )

        self.assertEqual(response.status_code, 404)


class InactiveRiderActionsTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            first_name="Admin",
            last_name="User",
            username="admin_user",
            email="admin@example.com",
            password="StrongPass123!",
        )
        self.admin_user.is_active = True
        self.admin_user.is_admin = True
        self.admin_user.save()

        self.staff_user = User.objects.create_user(
            first_name="Staff",
            last_name="User",
            username="staff_user",
            email="staff@example.com",
            password="StrongPass123!",
        )
        self.staff_user.is_active = True
        self.staff_user.is_staff = True
        self.staff_user.save()

        self.club = Club.objects.create(team_name="Inactive Club")
        self.other_club = Club.objects.create(team_name="Other Club")
        self.club_manager = User.objects.create_user(
            first_name="Club",
            last_name="Manager",
            username="club_manager",
            email="club_manager@example.com",
            password="StrongPass123!",
        )
        self.club_manager.is_active = True
        self.club_manager.is_club_manager = True
        self.club_manager.club = self.club
        self.club_manager.save()

        self.rider = Rider.objects.create(
            uci_id=12345678901,
            first_name="Inactive",
            last_name="Rider",
            gender="Muž",
            date_of_birth=date(2010, 5, 1),
            club=self.club,
            plate_text="145",
            is_active=True,
            is_approved=True,
            valid_licence=True,
        )
        Rider.objects.filter(pk=self.rider.pk).update(
            created=timezone.now() - timedelta(days=365 * 3)
        )
        self.other_club_rider = Rider.objects.create(
            uci_id=12345678902,
            first_name="Other",
            last_name="Club",
            gender="Muž",
            date_of_birth=date(2010, 5, 1),
            club=self.other_club,
            plate_text="146",
            is_active=True,
            is_approved=True,
            valid_licence=True,
        )
        Rider.objects.filter(pk=self.other_club_rider.pk).update(
            created=timezone.now() - timedelta(days=365 * 3)
        )

    def test_admin_can_deactivate_inactive_rider_from_list(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("rider:inactive-deactivate", kwargs={"rider_id": self.rider.pk}),
            follow=True,
        )

        self.rider.refresh_from_db()
        self.assertRedirects(response, reverse("rider:inactive"))
        self.assertFalse(self.rider.is_active)
        self.assertContains(response, "byl označen jako neaktivní")

    def test_staff_cannot_access_inactive_riders_page(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("rider:inactive"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_club_manager_sees_only_riders_from_own_club(self):
        self.client.force_login(self.club_manager)

        response = self.client.get(reverse("rider:inactive"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"{self.rider.first_name} {self.rider.last_name.upper()}")
        self.assertNotContains(
            response,
            f"{self.other_club_rider.first_name} {self.other_club_rider.last_name.upper()}",
        )

    def test_club_manager_can_deactivate_only_own_club_rider(self):
        self.client.force_login(self.club_manager)

        own_response = self.client.post(
            reverse("rider:inactive-deactivate", kwargs={"rider_id": self.rider.pk}),
            follow=True,
        )
        self.rider.refresh_from_db()

        blocked_response = self.client.post(
            reverse("rider:inactive-deactivate", kwargs={"rider_id": self.other_club_rider.pk}),
            follow=True,
        )
        self.other_club_rider.refresh_from_db()

        self.assertRedirects(own_response, reverse("rider:inactive"))
        self.assertFalse(self.rider.is_active)
        self.assertTrue(self.other_club_rider.is_active)
        self.assertContains(blocked_response, "nelze deaktivovat")

    def test_inactive_template_uses_external_script_and_no_inline_script(self):
        template = (
            Path(settings.BASE_DIR) / "rider" / "templates" / "rider" / "rider-inactive.html"
        ).read_text(encoding="utf-8")

        self.assertIn("js/rider_inactive.js", template)
        self.assertIn("data-release-form", template)
        self.assertIn("data-release-trigger", template)
        self.assertNotIn("<script>", template)
