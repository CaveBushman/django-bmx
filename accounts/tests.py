from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
import datetime
from io import BytesIO

from PIL import Image

from accounts.models import AccountRiderLink, AvatarChangeRequest
from club.models import Club
from rider.models import Rider


User = get_user_model()


class RememberMeLoginTests(TestCase):
    def setUp(self):
        self.password = "StrongPass123!"
        self.user = User.objects.create_user(
            first_name="Remember",
            last_name="Tester",
            username="remember_tester",
            email="remember@example.com",
            password=self.password,
        )
        self.user.is_active = True
        self.user.save()

    def test_login_with_remember_me_sets_persistent_session(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": self.user.email,
                "password": self.password,
                "remember-me": "on",
            },
        )

        self.assertRedirects(response, reverse("news:homepage"))
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertEqual(self.client.session.get_expiry_age(), 1209600)

    def test_login_without_remember_me_expires_at_browser_close(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": self.user.email,
                "password": self.password,
            },
        )

        self.assertRedirects(response, reverse("news:homepage"))
        self.assertTrue(self.client.session.get_expire_at_browser_close())


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

    def test_password_reset_sends_email(self):
        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": self.user.email},
        )

        self.assertRedirects(
            response,
            reverse("accounts:password_reset_done"),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Reset hesla na Czech BMX", mail.outbox[0].subject)
        self.assertIn("/accounts/reset/", mail.outbox[0].body)


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
