from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.contrib.sessions.middleware import SessionMiddleware
import datetime
import tempfile
from io import BytesIO

from PIL import Image

from accounts.admin import AccountAdmin, AvatarChangeRequestAdmin, PendingActivationAccountAdmin
from accounts.models import Account, AccountActivationAuditLog, AccountRiderLink, AvatarChangeRequest, PendingActivationAccount
from bmx.form_protection import build_flow_token
from club.models import Club
from event.models import Entry, Event
from rider.models import Rider


User = get_user_model()


class RememberMeLoginTests(TestCase):
    def setUp(self):
        self.password = "StrongPass123!"
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            first_name="Remember",
            last_name="Tester",
            username="remember_tester",
            email="remember@example.com",
            password=self.password,
        )
        self.user.is_active = True
        self.user.save()

    def login_payload(self, **overrides):
        payload = {
            "username": self.user.email,
            "password": self.password,
            "form_token": build_flow_token("signin", timezone.now() - datetime.timedelta(seconds=2)),
            "website": "",
        }
        payload.update(overrides)
        return payload

    def test_login_with_remember_me_sets_persistent_session(self):
        response = self.client.post(
            reverse("accounts:login"),
            self.login_payload(**{"remember-me": "on"}),
        )

        self.assertRedirects(response, reverse("news:homepage"))
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertEqual(self.client.session.get_expiry_age(), 1209600)

    def test_login_without_remember_me_expires_at_browser_close(self):
        response = self.client.post(
            reverse("accounts:login"),
            self.login_payload(),
        )

        self.assertRedirects(response, reverse("news:homepage"))
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_login_is_case_insensitive_for_email(self):
        response = self.client.post(
            reverse("accounts:login"),
            self.login_payload(username="REMEMBER@EXAMPLE.COM"),
        )

        self.assertRedirects(response, reverse("news:homepage"))

    def test_login_rejects_ambiguous_historical_email_duplicates(self):
        duplicate = User.objects.create_user(
            first_name="Remember",
            last_name="Duplicate",
            username="remember_duplicate",
            email="remember_duplicate@example.com",
            password=self.password,
        )
        duplicate.is_active = True
        duplicate.save(update_fields=["is_active"])
        User.objects.filter(pk=duplicate.pk).update(email="Remember@example.com")

        response = self.client.post(
            reverse("accounts:login"),
            self.login_payload(username="remember@example.com"),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        messages = list(response.context["messages"])
        self.assertTrue(any("více historických účtů" in str(message) for message in messages))

    def test_login_requires_human_check_after_repeated_failures(self):
        url = reverse("accounts:login")
        for _ in range(3):
            response = self.client.post(
                url,
                self.login_payload(password="bad-password"),
            )
            self.assertEqual(response.status_code, 200)

        challenge_response = self.client.post(
            url,
            self.login_payload(),
        )

        self.assertEqual(challenge_response.status_code, 400)
        self.assertContains(challenge_response, "human_check_answer")

    def test_login_inactive_account_shows_activation_message(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("accounts:login"),
            self.login_payload(),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        messages = list(response.context["messages"])
        self.assertTrue(any("ještě není aktivovaný" in str(message) for message in messages))


class AccountEmailNormalizationTests(TestCase):
    def test_create_user_normalizes_email_to_lowercase(self):
        user = User.objects.create_user(
            first_name="Email",
            last_name="Normalizer",
            username="email_normalizer",
            email="MixedCase@Example.COM",
            password="StrongPass123!",
        )

        self.assertEqual(user.email, "mixedcase@example.com")

    def test_clean_rejects_case_insensitive_duplicate_on_email_change(self):
        first_user = User.objects.create_user(
            first_name="First",
            last_name="User",
            username="first_user",
            email="first@example.com",
            password="StrongPass123!",
        )
        second_user = User.objects.create_user(
            first_name="Second",
            last_name="User",
            username="second_user",
            email="second@example.com",
            password="StrongPass123!",
        )

        second_user.email = "FIRST@example.com"
        with self.assertRaises(ValidationError):
            second_user.clean()

    def test_account_admin_search_ignores_case_and_diacritics(self):
        user = User.objects.create_user(
            first_name="Jiří",
            last_name="Novák",
            username="jiri_novak",
            email="jiri.novak@example.com",
            password="StrongPass123!",
        )

        request = RequestFactory().get("/admin/accounts/account/")
        request.user = user
        admin_instance = AccountAdmin(User, admin.site)

        queryset, _ = admin_instance.get_search_results(
            request,
            User.objects.all(),
            "NOVAK",
        )

        self.assertIn(user, list(queryset))

    def test_pending_activation_account_admin_filters_inactive_users(self):
        inactive_user = User.objects.create_user(
            first_name="Inactive",
            last_name="User",
            username="inactive_user",
            email="inactive@example.com",
            password="StrongPass123!",
        )
        active_user = User.objects.create_user(
            first_name="Active",
            last_name="User",
            username="active_user",
            email="active@example.com",
            password="StrongPass123!",
        )
        active_user.is_active = True
        active_user.save(update_fields=["is_active"])

        request = RequestFactory().get("/admin/accounts/pendingactivationaccount/")
        request.user = active_user
        admin_instance = PendingActivationAccountAdmin(PendingActivationAccount, admin.site)

        queryset = admin_instance.get_queryset(request)

        self.assertIn(inactive_user, list(queryset))
        self.assertNotIn(active_user, list(queryset))

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_account_admin_detail_resend_activation_view_sends_email(self):
        inactive_user = User.objects.create_user(
            first_name="Inactive",
            last_name="Detail",
            username="inactive_detail",
            email="inactive-detail@example.com",
            password="StrongPass123!",
        )
        admin_user = User.objects.create_user(
            first_name="Admin",
            last_name="Detail",
            username="admin_detail",
            email="admin-detail@example.com",
            password="StrongPass123!",
        )
        admin_user.is_staff = True
        admin_user.is_active = True
        admin_user.save(update_fields=["is_staff", "is_active"])
        self.client.force_login(admin_user)

        response = self.client.get(
            reverse("admin:accounts_account_resend_activation", args=[inactive_user.pk]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(
            AccountActivationAuditLog.objects.filter(
                account=inactive_user,
                action=AccountActivationAuditLog.Action.RESENT,
                source="admin_detail",
            ).exists()
        )


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetTests(TestCase):
    def setUp(self):
        self.password = "StrongPass123!"
        self.user = User.objects.create_user(
            first_name="Reset",
            last_name="Tester",
            username="reset_tester",
            email="reset@example.com",
            password=self.password,
        )
        self.user.is_active = True
        self.user.save()

    def reset_payload(self, **overrides):
        payload = {
            "email": self.user.email,
            "form_token": build_flow_token("password_reset", timezone.now() - datetime.timedelta(seconds=2)),
            "website": "",
        }
        payload.update(overrides)
        return payload

    def test_password_reset_sends_email(self):
        response = self.client.post(
            reverse("accounts:password_reset"),
            self.reset_payload(),
        )

        self.assertRedirects(
            response,
            reverse("accounts:password_reset_done"),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Reset hesla na Czech BMX", mail.outbox[0].subject)
        self.assertIn("/accounts/reset/", mail.outbox[0].body)

    def test_password_reset_requires_human_check_after_robot_attempts(self):
        url = reverse("accounts:password_reset")
        for _ in range(2):
            response = self.client.post(
                url,
                self.reset_payload(website="bot"),
            )
            self.assertEqual(response.status_code, 400)

        blocked = self.client.post(url, self.reset_payload())

        self.assertEqual(blocked.status_code, 400)
        self.assertContains(blocked, "human_check_answer")


class PendingActivationCleanupCommandTests(TestCase):
    def test_cleanup_pending_accounts_deletes_old_inactive_accounts(self):
        stale_user = User.objects.create_user(
            first_name="Stale",
            last_name="Pending",
            username="stale_pending",
            email="stale@example.com",
            password="StrongPass123!",
        )
        User.objects.filter(pk=stale_user.pk).update(
            is_active=False,
            date_joined=timezone.now() - datetime.timedelta(days=30),
        )

        fresh_user = User.objects.create_user(
            first_name="Fresh",
            last_name="Pending",
            username="fresh_pending",
            email="fresh@example.com",
            password="StrongPass123!",
        )
        User.objects.filter(pk=fresh_user.pk).update(
            is_active=False,
            date_joined=timezone.now() - datetime.timedelta(days=1),
        )

        call_command("cleanup_pending_accounts", days=7)

        self.assertFalse(User.objects.filter(pk=stale_user.pk).exists())
        self.assertTrue(User.objects.filter(pk=fresh_user.pk).exists())
        self.assertTrue(
            AccountActivationAuditLog.objects.filter(
                email_snapshot="stale@example.com",
                action=AccountActivationAuditLog.Action.CLEANED_UP,
            ).exists()
        )


class OpsDashboardTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            first_name="Ops",
            last_name="Admin",
            username="ops_admin",
            email="ops-admin@example.com",
            password="StrongPass123!",
        )
        self.staff_user.is_staff = True
        self.staff_user.is_active = True
        self.staff_user.save(update_fields=["is_staff", "is_active"])

    def test_ops_dashboard_requires_staff(self):
        response = self.client.get(reverse("accounts:ops_dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_ops_dashboard_renders_for_staff(self):
        club = Club.objects.create(team_name="Ops Club")
        AccountActivationAuditLog.objects.create(
            action=AccountActivationAuditLog.Action.SENT,
            source="signup",
            email_snapshot="pending@example.com",
        )
        avatar_target = User.objects.create_user(
            first_name="Avatar",
            last_name="Target",
            username="avatar_target",
            email="avatar-target@example.com",
            password="StrongPass123!",
        )
        AvatarChangeRequest.objects.create(
            uploaded_by=self.staff_user,
            target_account=avatar_target,
            image=SimpleUploadedFile("ops.png", b"fake-image", content_type="image/png"),
        )
        event = Event.objects.create(
            name="Ops Race",
            date=timezone.localdate() - datetime.timedelta(days=5),
            organizer=club,
            reg_open=False,
            type_for_ranking="Volný závod",
        )
        Rider.objects.create(
            uci_id=10101010101,
            first_name="Ops",
            last_name="Rider",
            gender="Muž",
            date_of_birth=timezone.localdate() - datetime.timedelta(days=3650),
            club=None,
            is_active=True,
            is_approved=True,
            valid_licence=True,
            photo="",
        )
        Entry.objects.create(
            user=self.staff_user,
            event=event,
            rider=None,
            payment_complete=False,
        )
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("accounts:ops_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Provozní dashboard")
        self.assertContains(response, "Co řešit hned")
        self.assertContains(response, "Avatar requesty")
        self.assertContains(response, "Poslední systémové změny")
        self.assertContains(response, "Souhrn chyb")
        self.assertContains(response, "Závody bez výsledků")
        self.assertContains(response, "Rychlý souhrn")


class AccountRiderLinkTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(team_name="BMX Test Club")
        self.user = User.objects.create_user(
            first_name="Parent",
            last_name="Account",
            username="parent_account",
            email="parent@example.com",
            password="StrongPass123!",
        )
        self.rider = Rider.objects.create(
            uci_id=123456789,
            first_name="Test",
            last_name="Rider",
            date_of_birth=datetime.date(2015, 1, 1),
            gender="Muž",
            club=self.club,
        )

    def test_account_can_be_linked_to_rider(self):
        AccountRiderLink.objects.create(account=self.user, rider=self.rider)

        self.assertEqual(self.user.riders.count(), 1)
        self.assertEqual(self.rider.linked_accounts.count(), 1)
        self.assertEqual(self.user.riders.first(), self.rider)
        self.assertEqual(self.rider.linked_accounts.first(), self.user)

    def test_same_rider_can_be_linked_to_multiple_accounts(self):
        second_user = User.objects.create_user(
            first_name="Second",
            last_name="Parent",
            username="second_parent",
            email="second_parent@example.com",
            password="StrongPass123!",
        )

        AccountRiderLink.objects.create(account=self.user, rider=self.rider)
        AccountRiderLink.objects.create(account=second_user, rider=self.rider)

        self.assertEqual(self.rider.linked_accounts.count(), 2)

    def test_duplicate_account_rider_link_is_rejected(self):
        AccountRiderLink.objects.create(account=self.user, rider=self.rider)

        with self.assertRaises(IntegrityError):
            AccountRiderLink.objects.create(account=self.user, rider=self.rider)


class AccountPhotoCleanupTests(TestCase):
    def _build_test_image(self, *, name="avatar.png", color=(40, 120, 220)):
        buffer = BytesIO()
        image = Image.new("RGB", (240, 240), color=color)
        image.save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def test_replacing_account_photo_deletes_previous_uploaded_file(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                user = User.objects.create_user(
                    first_name="Photo",
                    last_name="Cleanup",
                    username="photo_cleanup",
                    email="photo-cleanup@example.com",
                    password="StrongPass123!",
                )
                user.photo.save(
                    "old-avatar.png",
                    self._build_test_image(name="old-avatar.png"),
                    save=True,
                )
                old_name = user.photo.name
                self.assertTrue(user.photo.storage.exists(old_name))

                with self.captureOnCommitCallbacks(execute=True):
                    user.photo.save(
                        "new-avatar.png",
                        self._build_test_image(
                            name="new-avatar.png",
                            color=(120, 60, 220),
                        ),
                        save=True,
                    )

                self.assertFalse(user.photo.storage.exists(old_name))
                self.assertTrue(user.photo.storage.exists(user.photo.name))


@override_settings(SECURE_SSL_REDIRECT=False)
class AvatarChangeRequestTests(TestCase):
    def _build_test_image(self, *, name="avatar.png", color=(40, 120, 220)):
        buffer = BytesIO()
        image = Image.new("RGB", (240, 240), color=color)
        image.save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def setUp(self):
        self.user = User.objects.create_user(
            first_name="Avatar",
            last_name="Reviewer",
            username="avatar_reviewer",
            email="avatar_reviewer@example.com",
            password="StrongPass123!",
        )
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])
        self.club = Club.objects.create(team_name="Avatar Club")
        self.rider = Rider.objects.create(
            uci_id=12345678999,
            first_name="Avatar",
            last_name="Rider",
            date_of_birth=datetime.date(2015, 1, 1),
            gender="Muž",
            club=self.club,
        )

    def test_approve_updates_target_account_photo(self):
        request = AvatarChangeRequest.objects.create(
            uploaded_by=self.user,
            target_account=self.user,
            image=self._build_test_image(),
        )

        request.approve(self.user)

        self.user.refresh_from_db()
        request.refresh_from_db()
        self.assertEqual(request.status, AvatarChangeRequest.STATUS_APPROVED)
        self.assertIn("images/users/", self.user.photo.name)
        self.assertTrue(self.user.photo.name.endswith(".webp"))
        self.assertFalse(bool(request.image))

    def test_approve_updates_target_rider_photo_in_rider_storage(self):
        request = AvatarChangeRequest.objects.create(
            uploaded_by=self.user,
            target_rider=self.rider,
            image=self._build_test_image(name="rider-avatar.png", color=(120, 60, 220)),
        )

        request.approve(self.user)

        self.rider.refresh_from_db()
        request.refresh_from_db()
        self.assertEqual(request.status, AvatarChangeRequest.STATUS_APPROVED)
        self.assertIn("images/riders/", self.rider.photo.name)
        self.assertTrue(self.rider.photo.name.endswith(".webp"))
        self.assertFalse(bool(request.image))

    def test_only_one_pending_request_per_account_is_allowed(self):
        AvatarChangeRequest.objects.create(
            uploaded_by=self.user,
            target_account=self.user,
            image=self._build_test_image(name="first.png"),
        )

        with self.assertRaises(IntegrityError):
            AvatarChangeRequest.objects.create(
                uploaded_by=self.user,
                target_account=self.user,
                image=self._build_test_image(name="second.png"),
            )

    @override_settings(AVATAR_REQUEST_EXPIRATION_DAYS=30)
    def test_expire_stale_requests_marks_request_expired(self):
        stale_request = AvatarChangeRequest.objects.create(
            uploaded_by=self.user,
            target_rider=self.rider,
            image=self._build_test_image(name="stale.png"),
        )
        AvatarChangeRequest.objects.filter(pk=stale_request.pk).update(
            created=timezone.now() - timezone.timedelta(days=31)
        )

        expired_count = AvatarChangeRequest.expire_stale_requests()

        stale_request.refresh_from_db()
        self.assertEqual(expired_count, 1)
        self.assertEqual(stale_request.status, AvatarChangeRequest.STATUS_EXPIRED)
        self.assertFalse(bool(stale_request.image))

    def test_pending_avatar_admin_page_shows_only_pending_requests(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save(update_fields=["is_staff", "is_superuser"])
        self.client.force_login(self.user)

        pending_request = AvatarChangeRequest.objects.create(
            uploaded_by=self.user,
            target_account=self.user,
            image=self._build_test_image(name="pending.png"),
        )
        approved_request = AvatarChangeRequest.objects.create(
            uploaded_by=self.user,
            target_account=self.user,
            image=self._build_test_image(name="approved.png", color=(80, 160, 80)),
            status=AvatarChangeRequest.STATUS_APPROVED,
        )

        response = self.client.get(reverse("admin:accounts_pendingavatarchangerequest_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Čekající avatary")
        queryset = response.context["cl"].queryset
        self.assertEqual(list(queryset), [pending_request])
        self.assertNotIn(approved_request, queryset)

    def test_admin_change_form_approval_updates_target_account_photo(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save(update_fields=["is_staff", "is_superuser"])
        self.client.force_login(self.user)

        pending_request = AvatarChangeRequest.objects.create(
            uploaded_by=self.user,
            target_account=self.user,
            image=self._build_test_image(name="approve-via-admin-form.png"),
        )

        response = self.client.post(
            reverse("admin:accounts_avatarchangerequest_change", args=[pending_request.pk]),
            {
                "uploaded_by": self.user.pk,
                "target_account": self.user.pk,
                "target_rider": "",
                "status": AvatarChangeRequest.STATUS_APPROVED,
                "review_note": "approved in admin",
                "_save": "Save",
            },
            follow=True,
        )

        pending_request.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(pending_request.status, AvatarChangeRequest.STATUS_APPROVED)
        self.assertEqual(pending_request.reviewed_by, self.user)
        self.assertIsNotNone(pending_request.reviewed_at)
        self.assertFalse(bool(pending_request.image))
        self.assertTrue(self.user.photo.name.endswith(".webp"))

    def test_admin_bulk_approval_handles_invalid_image_without_server_error(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save(update_fields=["is_staff", "is_superuser"])

        invalid_request = AvatarChangeRequest.objects.create(
            uploaded_by=self.user,
            target_account=self.user,
            image=SimpleUploadedFile("broken.txt", b"not-an-image", content_type="text/plain"),
        )

        request = RequestFactory().post(reverse("admin:accounts_avatarchangerequest_changelist"))
        request.user = self.user
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))

        admin_instance = AvatarChangeRequestAdmin(AvatarChangeRequest, admin.site)
        admin_instance.approve_selected(request, AvatarChangeRequest.objects.filter(pk=invalid_request.pk))

        invalid_request.refresh_from_db()
        messages = [message.message for message in request._messages]

        self.assertEqual(invalid_request.status, AvatarChangeRequest.STATUS_PENDING)
        self.assertTrue(any("není platný obrázek" in message for message in messages))
        self.assertTrue(any("Selhalo: 1 žádostí." in message for message in messages))

    def test_staff_avatar_dashboard_shows_pending_requests(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.client.force_login(self.user)

        pending_request = AvatarChangeRequest.objects.create(
            uploaded_by=self.user,
            target_rider=self.rider,
            image=self._build_test_image(name="dashboard.png"),
        )

        response = self.client.get(reverse("accounts:avatar-moderation"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Schvalování avatarů")
        self.assertContains(response, pending_request.target_label)

    def test_staff_avatar_dashboard_can_approve_request(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.client.force_login(self.user)

        pending_request = AvatarChangeRequest.objects.create(
            uploaded_by=self.user,
            target_rider=self.rider,
            image=self._build_test_image(name="approve-via-dashboard.png"),
        )

        response = self.client.post(
            reverse("accounts:avatar-moderation"),
            {"action": "approve", "request_id": pending_request.pk},
            follow=True,
        )

        pending_request.refresh_from_db()
        self.rider.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(pending_request.status, AvatarChangeRequest.STATUS_APPROVED)
        self.assertTrue(self.rider.photo.name.endswith(".webp"))
