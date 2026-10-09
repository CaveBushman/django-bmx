"""Unit tests for accounts.push_notifications (previously ~12% covered)."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from accounts import push_notifications
from accounts.models import FcmDevice

User = get_user_model()


class ChunkTests(TestCase):
    def test_chunk_splits_into_batches(self):
        chunks = list(push_notifications._chunk(list(range(5)), 2))
        self.assertEqual(chunks, [[0, 1], [2, 3], [4]])

    def test_chunk_empty(self):
        self.assertEqual(list(push_notifications._chunk([], 3)), [])


class GetAppTests(TestCase):
    def setUp(self):
        push_notifications._firebase_app = None

    def tearDown(self):
        push_notifications._firebase_app = None

    @override_settings(FIREBASE_CREDENTIALS_JSON="", FIREBASE_CREDENTIALS_PATH="")
    def test_returns_none_when_not_configured(self):
        self.assertIsNone(push_notifications._get_app())

    def test_returns_cached_app(self):
        sentinel = object()
        push_notifications._firebase_app = sentinel
        self.assertIs(push_notifications._get_app(), sentinel)


class SendToTokensTests(TestCase):
    def setUp(self):
        push_notifications._firebase_app = None

    def tearDown(self):
        push_notifications._firebase_app = None

    def test_empty_tokens_short_circuits(self):
        result = push_notifications.send_to_tokens([], "t", "b")
        self.assertEqual(result, {"success": 0, "failure": 0, "total": 0})

    def test_no_app_counts_all_as_total(self):
        with patch.object(push_notifications, "_get_app", return_value=None):
            result = push_notifications.send_to_tokens(["a", "b"], "t", "b")
        self.assertEqual(result, {"success": 0, "failure": 0, "total": 2})

    def test_successful_send_and_stale_token_cleanup(self):
        user = User.objects.create_user(
            first_name="Push",
            last_name="User",
            username="push_user",
            email="push@example.com",
            password="StrongPass123!",
        )
        FcmDevice.objects.create(user=user, token="good-token")
        FcmDevice.objects.create(user=user, token="stale-token")

        good = SimpleNamespace(success=True, exception=None)
        stale = SimpleNamespace(
            success=False,
            exception=SimpleNamespace(code="registration-token-not-registered"),
        )
        fake_response = SimpleNamespace(
            success_count=1, failure_count=1, responses=[good, stale]
        )
        fake_messaging = MagicMock()
        fake_messaging.send_each_for_multicast.return_value = fake_response

        with patch.object(push_notifications, "_get_app", return_value=object()), patch.dict(
            "sys.modules", {"firebase_admin": MagicMock(messaging=fake_messaging)}
        ):
            # `from firebase_admin import messaging` resolves the attribute on the mock module
            import sys
            sys.modules["firebase_admin"].messaging = fake_messaging
            result = push_notifications.send_to_tokens(
                ["good-token", "stale-token"], "Title", "Body", path="/x"
            )

        self.assertEqual(result["success"], 1)
        self.assertEqual(result["failure"], 1)
        self.assertEqual(result["total"], 2)
        # stale token removed, good one kept
        self.assertFalse(FcmDevice.objects.filter(token="stale-token").exists())
        self.assertTrue(FcmDevice.objects.filter(token="good-token").exists())

    def test_batch_exception_counts_as_failures(self):
        fake_messaging = MagicMock()
        fake_messaging.send_each_for_multicast.side_effect = RuntimeError("boom")
        with patch.object(push_notifications, "_get_app", return_value=object()), patch.dict(
            "sys.modules", {"firebase_admin": MagicMock(messaging=fake_messaging)}
        ):
            import sys
            sys.modules["firebase_admin"].messaging = fake_messaging
            result = push_notifications.send_to_tokens(["a", "b"], "t", "b")
        self.assertEqual(result, {"success": 0, "failure": 2, "total": 2})


class SendToUsersTests(TestCase):
    def test_send_to_all_users_collects_all_tokens(self):
        user = User.objects.create_user(
            first_name="A",
            last_name="B",
            username="all_user",
            email="all@example.com",
            password="StrongPass123!",
        )
        FcmDevice.objects.create(user=user, token="tok1")
        FcmDevice.objects.create(user=user, token="tok2")

        with patch.object(push_notifications, "send_to_tokens", return_value={"ok": True}) as mock_send:
            push_notifications.send_to_all_users("t", "b", path="/p")

        tokens_arg = sorted(mock_send.call_args.args[0])
        self.assertEqual(tokens_arg, ["tok1", "tok2"])

    def test_send_to_users_filters_by_user_ids(self):
        u1 = User.objects.create_user(
            first_name="A", last_name="B", username="u1", email="u1@example.com", password="StrongPass123!"
        )
        u2 = User.objects.create_user(
            first_name="C", last_name="D", username="u2", email="u2@example.com", password="StrongPass123!"
        )
        FcmDevice.objects.create(user=u1, token="u1-tok")
        FcmDevice.objects.create(user=u2, token="u2-tok")

        with patch.object(push_notifications, "send_to_tokens", return_value={}) as mock_send:
            push_notifications.send_to_users([u1.id], "t", "b")

        self.assertEqual(list(mock_send.call_args.args[0]), ["u1-tok"])
